
import time

from android_world.agents import base_agent
from android_world.agents import infer
from android_world.env import interface
from android_world.env import json_action
from typing import Any, Optional
import re
from typing import  Optional
import json
import ast

PLAN_PROMPT_TEMPLATE = """# Role & Objective:
You are an AI agent designed to operate an Android phone on behalf of a user. Your primary responsibilities are:
- Answer questions: Respond to user queries (e.g., "What is my schedule for today?").
- Perform tasks: Complete actions on the phone to achieve user goals (e.g., setting an alarm).

# Action Framework:
When given a user request, you will execute it step-by-step. At each step, you will receive:
- Current screenshot
- Action history

Based on this information, you must select and execute one of the following actions (output in exact JSON format):
| Action Type          | Description                                                                 | JSON Format                                                                 |
|----------------------|-----------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| `open_app`           | Open an app from the <app_name_list>                                        | `{{"action_type":"open_app", "app_name": "<name>"}}`                         |
| `click`              | Tap a visible element (description should be unambiguous, containing shape, location, or distinguishing features) | `{{"action_type": "click", "target": "<description>"}}`                      |
| `long_press`         | Long-press a visible element (describe clearly)                             | `{{"action_type": "long_press", "target": "<description>"}}`                 |
| `input_text`         | Type into a field (this action contains clicking the text field, typing in the text and pressing the enter, so no need to click on the target field to start) | `{{"action_type": "input_text", "text": "<text>", "target": "<description>"}}`|
| `answer`             | Respond to user questions                                                   | `{{"action_type": "answer", "text": "<response>"}}`                          |
| `keyboard_enter`     | Press Enter key                                                             | `{{"action_type": "keyboard_enter"}}`                                        |
| `navigate_home`      | Return to home screen                                                       | `{{"action_type": "navigate_home"}}`                                         |
| `navigate_back`      | Navigate back                                                               | `{{"action_type": "navigate_back"}}`                                         |
| `scroll`             | Scroll in direction (up/down/left/right)                                    | `{{"action_type": "scroll", "direction": "<dir>"}}`                          |
| `wait`               | Wait for screen update                                                      | `{{"action_type": "wait"}}`                                                  |
| `status`             | Mark task as `complete` or `infeasible`.                                    | `{{"action_type": "status", "goal_status": "<status>"}}`                     |

# Operational Guidelines:
- **General:**
1. Usually there will be multiple ways to complete a task, pick the easiest one.
2. If a certain action fails twice in a row (visible in previous actions), then try alternative methods.  (e.g., use 'long_press' instead of 'click' or try alternative elements).
3. Sometimes you may need to navigate the phone to gather information needed to complete the task, for example if user asks "what is my schedule tomorrow", then you may want to open the calendar app (using the 'open_app' action), look up information there, answer user's question (using the 'answer' action) and finish (using the 'status' action with 'complete' as goal status).
4. Always use the 'answer' action to reply to user questions—never assume on-screen text suffices.
- **Action Related:**
1. Use 'open_app' with app_name from the provided <app_name_list> to launch installed apps instead of scrolling the screen up and down.
2. Prefer 'input_text' over manual keyboard clicks—even for passwords. If there is default text in the target field, delete it before typing. Refer to the **Text Related Operations** for the deletion method.
3. Use 'scroll' (with up/down/left/right) to reveal hidden content.The 'scroll' direction is inverse to swipe (e.g., scroll down to see lower content). If scrolling fails, try the opposite direction.
- **Text Related Operations**
1. To select some text: first enter selection mode by long_press near the target text. Some nearby words will be highlighted (with draggable range pointers), and a text selection bar will appear (options: 'Copy', 'Paste', 'Select All', etc.). Then adjust the selection by dragging the pointers. For full-field selection, tap 'Select All' in the bar. Arbitrary text selection is currently restricted due to no drag functionality.
2. To delete some text: first select the exact text you want to delete, which usually also brings up the text selection bar, then click the 'cut' button in bar.
3. To copy some text: first select the exact text you want to copy, which usually also brings up the text selection bar, then click the 'copy' button in bar.
4. To paste text into a text box, first long press the text box, then usually the text selection bar will appear with a ‘paste‘ button in it.

# Current Context:
- **User Goal**: `{goal}`
- **Previous Thoughts and Actions**: `{history}`
- **<app_name_list>**: `["Camera","Chrome","Clock","Contacts","Dialer","Files","Settings","Markor","Tasks","Simple Draw Pro","Simple Gallery Pro","Simple SMS Messenger","Audio Recorder","Pro Expense","Broccoli APP","OSMand","VLC","Joplin","Retro Music","OpenTracks","Simple Calendar Pro"]`
- **Current Time**: Today is October 15, Sunday, 2023, 23:34:00, which means it's the final day of this week.

# Start Task:
1. Analyze the user goal and current context. Examine the screenshot and previous thoughts & actions carefully.
2. Based on your analysis:
- If you determine that the task has been accomplished—for instance, the Wi-Fi is enabled, the photo thumbnail is detected in the interface's lower - right corner, the correct answer was given in prior actions, or the proper action has been carried out—use the 'complete' status action to finalize the task.
- if not, determine the most efficient next step to progress toward the goal. 
3. Select a single, precise action from the available options.
4. Output your answer.Your answer should be as follows (including just one set of a thought and an action):
Thought: ...\nAction: {{"action_type":...}}

Your Answer:
"""

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
) -> str:
    if history:
        history = '\n'.join(history)
    else:
        history = 'You just started, no action has been performed yet.'

    return PLAN_PROMPT_TEMPLATE.format(
        goal=goal,
        history=history
    )

def _command_to_json(
        plan_action:str,
        tool_call: str
) :
    try:
        string = tool_call.strip('()')
        x, y = map(int, string.split(','))
        plan_action_command = json.loads(plan_action)
        if plan_action_command['action_type'] in ['click','long_press']:
            return {'action_type': plan_action_command['action_type'], 'x': x, 'y': y}

        elif plan_action_command['action_type'] == 'input_text':
            return {'action_type': plan_action_command['action_type'],'text':plan_action_command['text'], 'x': x, 'y': y}
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

    def reset(self, go_home_on_reset: bool = False):
        super().reset(go_home_on_reset)
        self.env.hide_automation_ui()
        self.history = []

    def step(self, goal: str) -> base_agent.AgentInteractionResult:
        step_data = {
          'raw_screenshot': None,
          'plan_prompt': None,
          'plan_output':None,
          'plan_thought':None,
          'plan_action':None,
          'ground_output':None,
          'command':None
        }

        state = self.get_post_transition_state()  # 获取转换后的agent status 的便捷函数

        step_data['raw_screenshot'] = state.pixels.copy()
        before_screenshot = state.pixels.copy()


        print('----------step ' + str(len(self.history) + 1))

        # Planning 阶段

        plan_prompt = _plan_prompt(
            goal,
            self.history
        )
        step_data['plan_prompt'] = plan_prompt
        system_prompt = "You are a helpful assistant."
        plan_output, plan_is_safe, plan_raw_response = self.plan_llm.predict_mm(
            system_prompt = system_prompt,
            user_prompt =plan_prompt,
            images=[before_screenshot]
        )
        if not plan_raw_response:
            raise RuntimeError('Error calling LLM in planning phase.')
        step_data['plan_output'] = plan_output

        try:
            plan_thought = plan_output.split('Action:')[0].replace('Thought:','').strip()
            plan_action = plan_output.split('Action:')[1].strip()

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
        if plan_action_command['action_type'] in ['status','answer','keyboard_enter','navigate_home','navigate_back','wait','open_app','scroll']:
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
            command = ground_output.replace('Action:','').strip()
           
            if not command:
                print('Ground-Action prompt output is not in the correct format.')
                return base_agent.AgentInteractionResult(
                    False,
                    step_data,
                )

            
            step_data['command'] = command

            try:
                print(_command_to_json(plan_action,command))
                converted_action = json_action.JSONAction(
                    **_command_to_json(plan_action,command)
                )
                print("&&&& Converted_action &&&&: ", converted_action)
                step_data['action_output_json'] = converted_action
            except Exception as e:  
                print('Failed to convert the output to a valid action.')
                print(str(e))
                return base_agent.AgentInteractionResult(
                    False,
                    step_data,
                )

        if converted_action.action_type == 'status':
            if converted_action.goal_status == 'infeasible':
                print('Agent stopped since it thinks mission impossible.')  
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

        except Exception as e: 
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