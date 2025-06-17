from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import asyncio
import json
from typing import List, Dict, Optional, Tuple
import uuid
from pydantic import BaseModel
from loguru import logger
import gui_agent
import time
import sys
from threading import Thread
import uvicorn
import os
import signal


app = FastAPI()

logger.remove()
logger.add("./log/gui_agent_{time:YYYY-MM-DD}.log", encoding='utf-8', rotation='00:00',
           enqueue=True, context="spawn")


class Webclient:
    def __init__(self):
        self.websocket = None
        self.last_msg = None
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        self.reconnect_delay = 1  # seconds


    def update_websocket(self, websocket: WebSocket | None = None):
        self.websocket = websocket
        self.connected = websocket is not None
        if self.connected:
            self.reconnect_attempts = 0

    async def disconnect(self):
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
        self.websocket = None
        self.connected = False

    async def send_and_receive_msg(self, data: str) -> tuple[bool, str | None]:
        try:
            if not self.connected or self.websocket is None:
                return False, "WebSocket not connected"
            await self.websocket.send_text(data)


            current_time = time.time()
            while time.time() - current_time < 30:  # Wait for response for up to 30 seconds
                await asyncio.sleep(0.2)
                if self.last_msg is None:
                    continue
                return True, self.last_msg
        except WebSocketDisconnect:
            logger.warning("WebSocket disconnected during send_and_receive_msg")
            await self.disconnect()
            return False, "WebSocket disconnected"
        except Exception as e:
            logger.error(f"Error in send_and_receive_msg: {e}")
            await self.disconnect()
            return False, str(e)
        finally:
            self.last_msg = None
        return False, None

    def receive_msg(self, msg):
        self.last_msg = msg



client = Webclient()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await client.disconnect()
    await websocket.accept()
    client.update_websocket(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            client.receive_msg(data)
    except WebSocketDisconnect:
        logger.warning("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        client.update_websocket(None)

async def get_screenshot_api(
        taskId: str,
        requestId: str,
        is_screenshot_needed: bool = True,
        action: Optional[Dict] = None,
        ext: Optional[Dict] = None,
) -> Dict:
    """Send screenshot request to all connected clients and wait for response"""
    if action is None or action.get('action_type') == 'status':
        action = {}
    if ext is None:
        ext = {}

    request_data = {
        "taskId": taskId,
        "requestId": requestId,
        "is_screenshot_needed": is_screenshot_needed,
        "action": action,
        "ext": ext,
    }

    try:
        # Send request to the client

        print("截图请求已发送:",request_data)
        success, response = await client.send_and_receive_msg(json.dumps(request_data))
        print("code:",json.loads(response)['code'])
        if not success:
            return {"error": "No response from client"}
        return json.loads(response)
    except json.JSONDecodeError:
        return {"error": "Client returned invalid JSON"}
    except Exception as e:
        logger.error(f"Error in get_screenshot_api: {e}")
        return {"error": str(e)}


class Config:
    APP_CODE = "YOUR_APP_CODE"
    PLANNER_URL = "YOUR_PLANNER_URL"
    GROUNDER_URL = "YOUR_GROUNDER_URL"

class AgentRequest(BaseModel):
    modelId: str
    taskId: str
    goal: str
    ext: Optional[Dict] = None

def generate_request_id():
    return str(uuid.uuid4())

def generate_action_api(taskId:str,goal: str, screenshot: List[str], previous_actions: List[str]):
    """
        调用gui_agent.py 生成下一步action
        参数:
        goal (str): 目标描述
        screenshot (List[str]): 截图列表
        previous_actions (List[str]): 先前的动作列表
        """
    try:
        agent = gui_agent.GUIAgent(
            taskId,
            Config.APP_CODE,
            Config.PLANNER_URL,
            Config.GROUNDER_URL,
            goal,
            screenshot,
            previous_actions
        )
        previous_actions, action, plan_thought, plan_action = agent.step()
        # print("Previous Actions:",previous_actions)
        print("Current Actions:", action)
        return previous_actions, action, plan_thought, plan_action
    except Exception as e:
        print(f"GUI Agent API 时发生错误: {e}")
        return previous_actions, None


def restart_server():
    """重启服务器的函数"""
    logger.info("正在尝试重启服务器...")
    time.sleep(1)  # 等待1秒让原有服务完全关闭
    os.execv(sys.executable, ['python'] + sys.argv)


async def gui_agent_process(goal: str, taskId: str):
    try:

        previous_actions = []
        tasks = []
        i = 0
        print(f'Goal: {goal}')

        async def get_screenshot_api_wrapper(taskId, requestId, action):
            return await get_screenshot_api(taskId, requestId,action=action)

        action = None
        while True:
            try:
                requestId = generate_request_id()
                screenshot_response = await get_screenshot_api_wrapper(taskId, requestId, action = action)
                if 'screenshot' not in screenshot_response:
                    print(f"'screenshot' not in the {screenshot_response}")
                    return_data = {
                        "code": 200,
                        "taskId": taskId,
                        "requestId": requestId,
                        "is_finish": 1,
                        "messages": ["屏幕状态获取异常"]
                    }
                    yield json.dumps(return_data, ensure_ascii=False) + "\n\n"
                    break

                screenshot = screenshot_response['screenshot']
                i = i + 1
                previous_actions, action ,plan_thought, plan_action = generate_action_api(taskId,goal, [screenshot], previous_actions)
                log_info = {
                    "task_id":taskId,
                    "step_id":i,
                    "request_id":requestId,
                    "goal":goal,
                    "previous_actions":previous_actions,
                    "action":action,
                    "plan_thought":plan_thought,
                    "plan_action":plan_action,
                    # "screenshot":screenshot
                }
                logger.info(f"response info: {log_info}")

                task_name = plan_action

                if task_name:
                    task = {
                        "task_seq": "#E" + str(len(tasks) + 1),
                        "task_name": task_name,
                        "task_desc": task_name
                    }
                    tasks.append(task)

                    if action.get('action_type') in ['status']:
                    # if action.get('action_type') in ['answer']:
                        return_data = {
                            "code": 200,
                            "taskId": taskId,
                            "requestId": requestId,
                            "is_finish": 1,
                            "messages": tasks
                        }
                        yield  json.dumps(return_data, ensure_ascii=False) + "\n\n"
                        # 任务结束返回屏幕首页
                        screenshot_response = await get_screenshot_api_wrapper(taskId, requestId, action={"action_type": "navigate_home"})
                        break
                    else:
                        return_data = {
                            "code": 200,
                            "taskId": taskId,
                            "requestId": requestId,
                            "is_finish": 0,
                            "messages": tasks
                        }
                        yield json.dumps(return_data, ensure_ascii=False) + "\n\n"

                else:
                    return_data= {
                        "code": 200,
                        "taskId": taskId,
                        "requestId": requestId,
                        "is_finish": 0,
                        "messages": tasks
                    }
                    yield json.dumps(return_data, ensure_ascii=False) + "\n\n"

            except (GeneratorExit, asyncio.CancelledError):
                logger.warning("客户端断开连接，准备重启服务...")
                Thread(target=restart_server).start()
                break

            except Exception as e:
                logger.error(f"处理过程中出错: {e}")
                raise

    except Exception as e:
        logger.error(f"Error in gui_agent_process: {e}")
        await client.disconnect()
        raise



@app.post("/v1/gui_agent")
async def gui_agent_endpoint(request: AgentRequest):
    """SSE endpoint for GUI agent processing"""
    logger.info(f"AgentRequest: {request}")

    if not client.connected:
        return {"error": "WebSocket client not connected"}
    return StreamingResponse(
        gui_agent_process(request.goal, request.taskId),
        media_type="text/event-stream"
    )

def run_server():
    """Function to run the uvicorn server with error handling"""
    while True:
        try:
            uvicorn.run(app, host="0.0.0.0", port=8002)
        except Exception as e:
            logger.error(f"Server crashed with error: {e}")
            logger.info("Attempting to restart server in 5 seconds...")
            time.sleep(5)  # Wait before restarting
            continue
        else:
            # Clean exit
            break

def start_server_in_thread():
    """在新线程中启动服务器"""
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    return server_thread

if __name__ == "__main__":
    # 设置信号处理，捕获Ctrl+C
    def handle_sigint(signum, frame):
        logger.info("接收到中断信号，准备重启服务...")
        Thread(target=restart_server).start()

    signal.signal(signal.SIGINT, handle_sigint)

    # 启动服务器
    server_thread = start_server_in_thread()

    try:
        while True:
            time.sleep(1)
            if not server_thread.is_alive():
                logger.warning("服务器线程已停止，准备重启...")
                server_thread = start_server_in_thread()
    except KeyboardInterrupt:
        logger.info("收到键盘中断，退出主线程")
        sys.exit(0)
