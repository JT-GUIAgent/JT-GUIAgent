import json
import requests
import time
import base64
from typing import List, Optional, Union

ERROR_CALLING_LLM = 'Error calling LLM'

class PlannerWrapper:
    RETRY_WAITING_SECONDS = 20
    MAX_RETRIES = 3
    DEFAULT_TEMPERATURE = 0.01
    DEFAULT_MODEL = 'PLANNER'

    def __init__(self, app_code: str, url: str,
                 temperature: float = DEFAULT_TEMPERATURE,
                 model: str = DEFAULT_MODEL):
        self.app_code = app_code
        self.url = url
        self.temperature = temperature
        self.model = model


    def _create_payload(self, system_prompt: str, user_prompt: str,
                        images_base64: List[str]) -> dict:
        """Create the API request payload."""
        content = [{'type': 'text', 'text': json.dumps(user_prompt, ensure_ascii=False)}]

        for image_base64 in images_base64:
            content.append({
                'type': 'image_url',
                'image_url': {
                    'url': f'data:image/jpeg;base64,{image_base64}'
                },
            })

        return {
            'model': self.model,
            'temperature': self.temperature,
            'messages': [
                {"role": "system", "content": json.dumps(system_prompt, ensure_ascii=False)},
                {'role': 'user', 'content': content}
            ],
            'max_new_tokens': 1024,
        }

    def predict(self, system_prompt: str, user_prompt: str,
                images_base64: List[str]) -> Union[str, dict]:
        """
        Make a prediction call to the LLM API.

        Args:
            system_prompt: The system prompt
            user_prompt: The user prompt
            images_base64: List of base64 encoded image strings

        Returns:
            API response content or error message
        """
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {self.app_code}",
        }

        payload = self._create_payload(system_prompt, user_prompt, images_base64)

        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.post(
                    self.url,
                    headers=headers,
                    json=payload,
                    timeout=30
                )

                if response.ok:
                    response_json = response.json()
                    if 'choices' in response_json:
                        return response_json['choices'][0]['message']['content']
                    elif 'error' in response_json:
                        print(f"API Error: {response_json['error']['message']}")

                # Exponential backoff
                wait_time = self.RETRY_WAITING_SECONDS * (2 ** attempt)
                time.sleep(wait_time)

            except requests.exceptions.RequestException as e:
                print(f"Request failed (attempt {attempt + 1}): {str(e)}")
                wait_time = self.RETRY_WAITING_SECONDS * (2 ** attempt)
                time.sleep(wait_time)

        return ERROR_CALLING_LLM



class GrounderWrapper:
    RETRY_WAITING_SECONDS = 20
    MAX_RETRIES = 3
    DEFAULT_TEMPERATURE = 0.01
    DEFAULT_MODEL = 'GROUNDER'


    def __init__(self, app_code: str, url: str,
                 temperature: float = DEFAULT_TEMPERATURE,
                 model: str = DEFAULT_MODEL):
        self.app_code = app_code
        self.url = url
        self.temperature = temperature
        self.model = model


    def _create_payload(self, system_prompt: str, user_prompt: str,
                        images_base64: List[str]) -> dict:
        """Create the API request payload."""
        content = [{'type': 'text', 'text': json.dumps(user_prompt, ensure_ascii=False)}]
        # print(content)

        for image_base64 in images_base64:
            content.append({
                'type': 'image_url',
                'image_url': {
                    'url': f'data:image/jpeg;base64,{image_base64}'
                },
            })

        return {
            'model': self.model,
            'temperature': self.temperature,
            'messages': [
                {"role": "system", "content": json.dumps(system_prompt, ensure_ascii=False)},
                {'role': 'user', 'content': content}
            ],
            'max_tokens': 1024,
        }

    def predict(self, system_prompt: str, user_prompt: str,
                images_base64: List[str]) -> Union[str, dict]:
        """
        Make a prediction call to the LLM API.

        Args:
            system_prompt: The system prompt
            user_prompt: The user prompt
            images_base64: List of base64 encoded image strings

        Returns:
            API response content or error message
        """
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {self.app_code}",
        }

        payload = self._create_payload(system_prompt, user_prompt, images_base64)

        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.post(
                    self.url,
                    headers=headers,
                    json=payload,
                    timeout=30
                )

                if response.ok:
                    response_json = response.json()
                    if 'choices' in response_json:
                        return response_json['choices'][0]['message']['content']
                    elif 'error' in response_json:
                        print(f"API Error: {response_json['error']['message']}")

                # Exponential backoff
                wait_time = self.RETRY_WAITING_SECONDS * (2 ** attempt)
                time.sleep(wait_time)

            except requests.exceptions.RequestException as e:
                print(f"Request failed (attempt {attempt + 1}): {str(e)}")
                wait_time = self.RETRY_WAITING_SECONDS * (2 ** attempt)
                time.sleep(wait_time)

        return ERROR_CALLING_LLM


