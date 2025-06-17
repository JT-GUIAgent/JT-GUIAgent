
import json
import model
from typing import List, Dict, Optional, Tuple
import datetime
import pandas as  pd
import os
import base64

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
- **Current Time**: {current_time}

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


def _plan_prompt(goal: str, history: List[str]) -> str:
    history_str = '\n'.join(history) if history else 'You just started, no action has been performed yet.'
    # history_str = '\n'.join(history[-3:]) if history else 'You just started, no action has been performed yet.'
    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
    return PLAN_PROMPT_TEMPLATE.format(goal=goal, history=history_str,current_time=formatted_time)


def _command_to_json(plan_action: str, command: str) -> Optional[Dict]:
        try:
            string = command.strip('()')
            x, y = map(int, string.split(','))
            plan_action_command = json.loads(plan_action)
            action_type = plan_action_command['action_type']

            if action_type in ['click', 'long_press']:
                return {'action_type': action_type, 'x': x, 'y': y}
            elif action_type == 'input_text':
                return {
                    'action_type': action_type,
                    'text': plan_action_command['text'],
                    'x': x,
                    'y': y
                }
            return None
        except (ValueError, json.JSONDecodeError, KeyError):
            return None


class GUIAgent:
    def __init__(self,task_id:str,app_code: str , planner_url: str, grounder_url: str, goal: str, screenshot: List[str], previous_actions: List[str],):

        self.plan_llm = model.PlannerWrapper(app_code=app_code, url=planner_url)
        self.ground_llm = model.GrounderWrapper(app_code=app_code, url=grounder_url)
        self.previous_actions = previous_actions.copy()
        self.goal = goal
        self.screenshot = screenshot
        self.task_id = task_id


    def step(self):
        step_num = len(self.previous_actions) + 1
        print(f'----------step {step_num}')

        # Planning phase
        plan_prompt = _plan_prompt(self.goal, self.previous_actions)
        system_prompt = "You are a helpful assistant."
        screenshot = self.screenshot
        try:

            plan_output = self.plan_llm.predict(
                system_prompt=system_prompt,
                user_prompt=plan_prompt,
                images_base64=screenshot
            )

        except Exception as e:
            raise RuntimeError(f'Error calling LLM in planning phase: {str(e)}')

        if not plan_output:
            raise RuntimeError('No response received from LLM in planning phase.')

        try:
            plan_thought = plan_output.split('Action:')[0].replace('Thought:','').strip()
            plan_action = plan_output.split('Action:')[1].split('Thought:')[0].strip()

        except IndexError:
            print("Plan-Action prompt output is not in the correct format.")
            return self.previous_actions, None,None,None

        print(f'Plan_Thought: {plan_thought}')
        print(f'Plan_Action: {plan_action}')

        try:
            plan_action_command = json.loads(plan_action)
            action_type = plan_action_command.get('action_type', '')
            if action_type in ['status', 'answer', 'keyboard_enter', 'navigate_home', 'navigate_back', 'wait',  'scroll','open_app','input_text']:
                final_action = plan_action_command
            else:
                # Grounding phase
                ground_system_prompt = GROUND_SYSTEM_PROMPT
                target = plan_action_command.get('target', '')

                ground_user_prompt = GROUND_USER_PROMPT.format(plan_action=target)
                try:
                    ground_output = self.ground_llm.predict(
                        system_prompt=ground_system_prompt,
                        user_prompt=ground_user_prompt,
                        images_base64=screenshot
                    )
                except Exception as e:
                    raise RuntimeError(f'Error calling LLM in grounding phase: {str(e)}')

                if not ground_output:
                    raise RuntimeError('No response received from LLM in grounding phase.')

                command = ground_output.replace('Action:', '').strip()

                if not command:
                    print('Ground-Action prompt output is not in the correct format.')
                    return self.previous_actions, None

                final_action = _command_to_json(plan_action, command)

        except json.JSONDecodeError:
            print("Invalid JSON in plan action.")
            return self.previous_actions, None

        # history_entry = {
        #     "Thought": plan_thought,
        #     "Action": plan_action
        # }
        history_entry = plan_action
        # self.previous_actions.append(f'Step {step_num}: {json.dumps(history_entry, ensure_ascii=False)}')
        self.previous_actions.append(f'Step {step_num}: {history_entry}')


        # save
        save_dir = 'image_save/'
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        image_name = self.task_id+'_'+str(step_num)+'.jpg'
        image_save_path = os.path.join(save_dir, image_name)

        base64_data = screenshot[0]
        if base64_data.startswith('data:'):
            base64_data = base64_data.split(',', 1)[1]
        image_data = base64.b64decode(base64_data)
        with open(image_save_path, 'wb') as f:
            f.write(image_data)

        print(f"图片已成功保存到: {image_save_path}")


        new_row = {
            'task_id':self.task_id,
            'goal':self.goal,
            'step_num':step_num,
            'plan_thought':plan_thought,
            'plan_action_command': plan_action_command,
            'final_action': final_action,
            'image_paths': image_save_path
        }
        try:
            df = pd.DataFrame([new_row])
            excel_path = 'record_trace.xlsx'

            if not os.path.exists(excel_path):
                df.to_excel(excel_path, index=False)
            else:
                with pd.ExcelWriter(excel_path, mode='a', engine='openpyxl',
                                    if_sheet_exists='overlay') as writer:
                    sheet_name = writer.sheets['Sheet1'].title
                    startrow = writer.sheets[sheet_name].max_row
                    df.to_excel(writer, index=False, header=False, startrow=startrow)

        except Exception as e:
            print(f"保存到Excel失败: {str(e)}")

        return self.previous_actions, final_action , plan_thought, plan_action_command
