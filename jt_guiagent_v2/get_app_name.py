import  os
import json
import model

app_code =""
url = ""

APP_NAME_LIST = ["Camera","Chrome","Clock","Contacts","Dialer","Files","Settings","Markor","Tasks","Simple Draw Pro","Simple Gallery Pro","Simple SMS Messenger","Audio Recorder","Pro Expense","Broccoli APP","OSMand","VLC","Joplin","Retro Music","OpenTracks","Simple Calendar Pro"]

PROMPT_TEMPLATE = """You will be given a task description and a list of installed apps. 
Analyze the task and determine which app from the provided list should be opened first to accomplish it.
Respond ONLY with a JSON object in the exact format: {{"app_name": "app_name_from_the_list"}}.

Remember:
1. Choose the most relevant app that would be opened first to begin the task
2. Use the exact app name as provided in the list
3. Only respond with the JSON object, no additional text or explanations

Task Description: I need to book a flight to New York next week
App List: Photos, Calendar, Kayak, Messages, Email

Expected response:
{{"app_name": "Kayak"}}

Task Description: {goal}
App List: {APP_NAME_LIST}
Expected response:"""


class APPNAMEFinder():
    def __init__(self):
        self.llm = model.GrounderWrapper(app_code=app_code, url=url)

    def get_app_name(self, goal: str):
        prompt = PROMPT_TEMPLATE.format(goal=goal,APP_NAME_LIST=APP_NAME_LIST)
        system_prompt = "You are a helpful assistant."
        output, is_safe, raw_response = self.llm.predict(
            system_prompt = system_prompt,
            user_prompt =prompt,
            images_base64=[]
        )
        output = output.replace('```json','').replace('```','').strip()
        print(output)
        return json.loads(output)['app_name']
