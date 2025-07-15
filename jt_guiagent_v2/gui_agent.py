
import json
import model
from typing import List, Dict, Optional, Tuple
import datetime
import pandas as  pd
import os
import base64
import get_app_name

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
- Current Time: {current_time}
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


def _plan_prompt(goal: str, history: List[str],ref_app_name: str,ref_usage_notes: str) -> str:
    history_str = '\n'.join(history) if history else 'You just started, no action has been performed yet.'
    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
    return PLAN_PROMPT_TEMPLATE.format(goal=goal, history=history_str,current_time=formatted_time,ref_app_name = ref_app_name,
        ref_usage_notes = ref_usage_notes)


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
        self.ref_appname_finder = get_app_name.APPNAMEFinder()
        self.app_guidance_excel = 'APP_Usage_Guide_KB.xlsx'
        self.ref_app_name = None
        self.ref_usage_notes = None


    def step(self):
        step_num = len(self.previous_actions) + 1

        if not self.ref_app_name:
            self.ref_app_name = self.ref_appname_finder.get_app_name(self.goal)
            df = pd.read_excel(self.app_guidance_excel)
            mask = df['app_name'].str.strip().str.lower() == self.ref_app_name.strip().lower()
            matches = df[mask]
            self.ref_usage_notes =  matches.iloc[0]['usage_notes']

        # Planning phase
        plan_prompt = _plan_prompt(
            self.goal,
            self.previous_actions,
            self.ref_app_name,
            self.ref_usage_notes
        )
        screenshot = self.screenshot

        if self.ref_app_name and self.previous_actions == []:

            plan_action_command = {"action_type":"open_app","app_name":self.ref_app_name}
            plan_action = json.dumps(plan_action_command,ensure_ascii=False)
            plan_thought = None
            print('----------step ' + str(len(self.previous_actions) + 1))

        else:

            system_prompt = "You are a helpful assistant."

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


        history_entry = plan_action
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
