import time

from android_world.agents import base_agent
from android_world.agents import infer
from android_world.env import interface
from android_world.env import json_action
from android_world.agents import get_app_name
import json
import pandas as pd

PLAN_PROMPT_TEMPLATE = """# Role: Android Phone Operator AI
You are an AI that controls an Android phone to complete user requests. Your responsibilities:
- Answer questions by retrieving information from the phone.
- Perform tasks by executing precise actions.

# Action Framework
Respond with EXACT JSON format for one of these actions:
| Action          | Description                              | JSON Format Example                                                         |
|-----------------|----------------------------------------- |-----------------------------------------------------------------------------|
| `open_app`      | Open app from <Available Apps>           | `{{"action_type":"open_app", "app_name": "Chrome"}}`                        |
| `click`         | Tap visible element (describe clearly)   | `{{"action_type": "click", "target": "blue circle button at top-right"}}`   |
| `long_press`    | Long-press visible element               | `{{"action_type": "long_press", "target": "message from John"}}`            |
| `input_text`    | Type into field (This action includes clicking the text field, typing, and pressing enter—no need to click the target field first.) | `{{"action_type":"input_text", "text":"Hello", "target":"message input box"}}`|
| `answer`        | Respond to user                          | `{{"action_type":"answer", "text":"It's 25 degrees today."}}`               |
| `keyboard_enter`| Press Enter key                          | `{{"action_type": "keyboard_enter"}}`                                       |
| `navigate_home` | Return to home screen                    | `{{"action_type": "navigate_home"}}`                                        |
| `navigate_back` | Navigate back                            | `{{"action_type": "navigate_back"}}`                                        |
| `scroll`        | Scroll direction (up/down/left/right)    | `{{"action_type":"scroll", "direction":"down"}}`                            |
| `wait`          | Wait for screen update                   | `{{"action_type": "wait"}}`                                                 |
| `status`        | Mark task as `complete` or `infeasible`  | `{{"action_type":"status", "goal_status":"complete"}}`                      |

# Execution Principles
1.Communication Rule:
   - ALWAYS use 'answer' action to reply to users - never assume on-screen text is sufficient

2.Efficiency First:
   - Choose simplest path to complete tasks
   - If action fails twice, try alternatives (e.g., long_press instead of click)

3. Smart Navigation:
   - Use `open_app` with provided available app list instead of manual navigation
   - Gather information when needed (e.g., open Calendar to check schedule)
   - For scrolling:
     * Scroll direction is INVERSE to swipe (scroll down to see lower content)
     * If scroll fails, try opposite direction

4. Text Operations:
   - Prefer `input_text` over manual typing
   - For text manipulation:
     1. Long-press to select
     2. Use selection bar options (Copy/Paste/Select All)
     3. Delete by selecting then cutting

5. App Usage Guidance:
   - Carefully review the app_name and usage_notes in App Usage Guide
   - Use them as guidance but adapt to actual screen content
   - When guidance conflicts with actual situation, prioritize what you see on screen


# Current Context
- User Goal: `{goal}`
- Previous Actions: `{history}`
- Available Apps: `["Camera","Chrome","Clock","Contacts","Dialer","Files","Settings","Markor","Tasks","Simple Draw Pro","Simple Gallery Pro","Simple SMS Messenger","Audio Recorder","Pro Expense","Broccoli APP","OSMand","VLC","Joplin","Retro Music","OpenTracks","Simple Calendar Pro"]`
- Current Time: October 15, Sunday, 2023, 23:34:00
- App Usage Guide:
  - app_name: `{ref_app_name}`
  - usage_notes: `{ref_usage_notes}`


# Decision Process
1. Analyze goal, history, and current screen
2. Check App Usage Guide's app_name and usage_notes for guidance
3. Determine if task is already complete (use `status` if true)
4. If not, choose the most efficient next action considering:
   - App Usage Guide
   - Actual screen content
   - Previous failures
5. Output in exact format:

Thought: [Analysis including reference to key steps/points when applicable]
Action: [Single JSON action]

Your Response:"""

GROUND_SYSTEM_PROMPT = """You are a helpful assistant."""

GROUND_USER_PROMPT = """Your task is to help the user identify the precise coordinates (x, y) of a specific area/element/object on the screen based on a description.

- If the description is unclear or ambiguous, infer the most relevant area or element based on its likely context or purpose.
- Your answer should be a single string (x, y) corresponding to the point of the interest.

Description: {plan_action}

Answer:
"""


def _plan_prompt(
        goal: str,
        history: list[str],
        ref_app_name: str,
        ref_usage_notes: str
) -> str:
    if history:
        history = '\n'.join(history)  # [-5:]
    else:
        history = 'You just started, no action has been performed yet.'

    return PLAN_PROMPT_TEMPLATE.format(
        goal=goal,
        history=history,
        ref_app_name=ref_app_name,
        ref_usage_notes=ref_usage_notes
    )


def _command_to_json(
        plan_action: str,
        tool_call: str
):
    try:
        tool_call = tool_call.replace('[', '(').replace(']', ')')
        string = tool_call.strip('()')
        x, y = map(int, string.split(','))
        plan_action_command = json.loads(plan_action)
        if plan_action_command['action_type'] in ['click', 'long_press']:
            return {'action_type': plan_action_command['action_type'], 'x': x, 'y': y}

        elif plan_action_command['action_type'] == 'input_text':
            return {'action_type': plan_action_command['action_type'],
                    'text': plan_action_command['text'].replace('\n', ''), 'x': x, 'y': y}
        else:
            return None
    except:
        return None


class PGAgent(base_agent.EnvironmentInteractingAgent):
    """Planning + Grounding agent"""

    def __init__(
            self,
            env: interface.AsyncEnv,
            plan_llm: infer.PlannerWrapper,
            ground_llm: infer.GrounderWrapper,
            name: str = 'PG_agent',
            wait_after_action_seconds: float = 2.0,
    ):
        super().__init__(env, name)
        self.plan_llm = plan_llm
        self.ground_llm = ground_llm
        self.history = []
        self.wait_after_action_seconds = wait_after_action_seconds
        self.ref_app_name = None
        self.ref_usage_notes = None
        self.ref_appname_finder = get_app_name.APPNAMEFinder(llm=ground_llm)
        self.app_guidance_excel = 'APP_Usage_Guide_KB.xlsx'

    def reset(self, go_home_on_reset: bool = False):
        super().reset(go_home_on_reset)

        self.env.hide_automation_ui()
        self.history = []
        self.ref_app_name = None
        self.ref_usage_notes = None

    def step(self, goal: str) -> base_agent.AgentInteractionResult:
        if not self.ref_app_name:
            self.ref_app_name = self.ref_appname_finder.get_app_name(goal)
            df = pd.read_excel(self.app_guidance_excel)
            mask = df['app_name'].str.strip().str.lower() == self.ref_app_name.strip().lower()
            matches = df[mask]
            self.ref_usage_notes = matches.iloc[0]['usage_notes']

        print("ref_app_name:", self.ref_app_name)
        print("ref_usage_notes:", self.ref_usage_notes)

        step_data = {
            'raw_screenshot': None,
            'plan_prompt': None,
            'plan_output': None,
            'plan_thought': None,
            'plan_action': None,
            'ground_output': None,
            'command': None
        }
        plan_prompt = _plan_prompt(
            goal,
            self.history,
            self.ref_app_name,
            self.ref_usage_notes
        )

        if self.ref_app_name != 'None' and self.history == []:

            plan_action_command = {"action_type": "open_app", "app_name": self.ref_app_name}
            plan_action = json.dumps(plan_action_command, ensure_ascii=False)
            print('----------step ' + str(len(self.history) + 1))
            converted_action = json_action.JSONAction(
                **plan_action_command
            )
            print("&&&& Converted_action &&&&: ", converted_action)
            step_data['action_output_json'] = converted_action

        else:

            state = self.get_post_transition_state()  # 获取转换后的agent status 的便捷函数

            step_data['raw_screenshot'] = state.pixels.copy()
            before_screenshot = state.pixels.copy()

            print('----------step ' + str(len(self.history) + 1))

            # Planning 阶段

            step_data['plan_prompt'] = plan_prompt
            system_prompt = "You are a helpful assistant."
            plan_output, plan_is_safe, plan_raw_response = self.plan_llm.predict_mm(
                system_prompt=system_prompt,
                user_prompt=plan_prompt,
                images=[before_screenshot]
            )
            if not plan_raw_response:
                raise RuntimeError('Error calling LLM in planning phase.')
            step_data['plan_output'] = plan_output

            try:
                plan_thought = plan_output.split('Action:')[0].replace('Thought:', '').strip()
                plan_action = plan_output.split('Action:')[1].replace('```json', '').replace('```', '').strip()

            except Exception as e:
                print("Plan-Action prompt output is not in the correct format.")
                return base_agent.AgentInteractionResult(
                    False,
                    step_data,
                )
            print('Plan_Thought: ' + plan_thought)
            print('Plan_Action: ' + plan_action)

            step_data['plan_thought'] = plan_thought
            step_data['plan_action'] = plan_action

            plan_action_command = json.loads(plan_action)
            if plan_action_command['action_type'] in ['status', 'answer', 'keyboard_enter', 'navigate_home',
                                                      'navigate_back', 'wait', 'open_app', 'scroll']:
                converted_action = json_action.JSONAction(
                    **plan_action_command
                )
                print("&&&& Converted_action &&&&: ", converted_action)
                step_data['action_output_json'] = converted_action
                # print("Previous_actions: ", self.history[-5:])

            else:
                # Grounding 阶段
                ground_system_prompt = GROUND_SYSTEM_PROMPT
                ground_user_prompt = GROUND_USER_PROMPT.format(plan_action=json.loads(plan_action)['target'])

                ground_output, is_safe, ground_raw_response = self.ground_llm.predict_mm(
                    system_prompt=ground_system_prompt,
                    user_prompt=ground_user_prompt,
                    images=[before_screenshot]
                )

                if not ground_raw_response:
                    raise RuntimeError('Error calling LLM in grounding phase.')

                step_data['ground_output'] = ground_output
                command = ground_output.replace('Action:', '').strip()
                # tool_call_pattern = re.compile(r'<tool_call>(.*?)</tool_call>', re.DOTALL)
                # command = tool_call_pattern.search(ground_output).group(1).strip().replace("\n", "").replace("\\", "")

                if not command:
                    print('Ground-Action prompt output is not in the correct format.')
                    return base_agent.AgentInteractionResult(
                        False,
                        step_data,
                    )

                # print("command: ", command)
                # print("Previous_actions: ", self.history[-5:])
                step_data['command'] = command

                try:
                    print(_command_to_json(plan_action, command))
                    converted_action = json_action.JSONAction(
                        **_command_to_json(plan_action, command)
                    )
                    print("&&&& Converted_action &&&&: ", converted_action)
                    step_data['action_output_json'] = converted_action
                except Exception as e:  # pylint: disable=broad-exception-caught

                    print('Failed to convert the output to a valid action.')
                    print(str(e))
                    return base_agent.AgentInteractionResult(
                        False,
                        step_data,
                    )

        if converted_action.action_type == 'status':
            if converted_action.goal_status == 'infeasible':
                print('Agent stopped since it thinks mission impossible.')  # 智能体已停止，因为它认为任务不可能完成。
            return base_agent.AgentInteractionResult(
                True,
                step_data,
            )
        if converted_action.action_type == 'answer':
            print('Agent answered with: ' + converted_action.text)
        # history_i= '{"Thought":'+plan_thought+',"Action":'+plan_action+'}'
        history_i = plan_action
        self.history.append('Step ' + str(len(self.history) + 1) + ': ' + history_i)
        step_data['history'] = self.history

        try:
            self.env.execute_action(converted_action)

        except Exception as e:  # pylint: disable=broad-exception-caught
            print('Failed to execute action.')
            print(str(e))
            return base_agent.AgentInteractionResult(
                False,
                step_data,
            )

        time.sleep(self.wait_after_action_seconds)

        return base_agent.AgentInteractionResult(
            False,
            step_data,
        )
