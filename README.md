# JT-GUIAgent-V1

<img src="./images/jiutian_logo.png" alt="Jiutian Logo" width="200">

[Project Page](https://jt-guiagent.github.io/JT_guiagent.github.io/) | [Code](https://github.com/JT-GUIAgent/JT-GUIAgent-V1)  

## ✨ Overview  

JT-GUIAgent-V1 is an advanced GUI Agent developed by China Mobile's Jiutian, built upon a multimodal large language model (LLM) and featuring an innovative two-phase collaborative framework. By decoupling autonomous decision-making into global planning (Planner) and local grounding (Grounder), the system achieves:

- Systematic task execution for complex workflows
- Reduced confusion and improved accuracy
- Modular design for flexible adaptation
- Independent optimization of components

## ✨ Architecture  

<img src="./images/workflow.png" alt="JT-GUIAgent Workflow" style="max-width: 80%; display: block; margin: 0 auto;">

### Key Components

**Planner: High-Level Task Orchestration**  
Features a structured prompt template with:

- Intelligent action space selection
- Multi-step task decomposition
- Execution guidelines
- Chain-of-thought reasoning

**Grounder: Precise Element Localization**  
Utilizes an enhanced training strategy with:

- Open-source UI datasets + synthetic Chinese app data
- Benchmark performance (ScreenSpot-V2):
  - 📱 97.2% text component accuracy
  - 🖼️ 82.5% icon component accuracy

## ✨ Performance Highlights  

**Benchmark Results** 
 
- ✅ 60% end-to-end success rate in [AndroidWorld](https://github.com/google-research/android_world)  
- 🏆 Reliable execution of complex real-world tasks:
  - Video playback
  - Travel booking (flights/hotels)
  - Ticket purchasing
  - ...

## ✨ Case Studies  

### AndroidWorld Benchmark Tasks

| Difficulty | User Instruction | Demo Link |
|------------|-------------|-----------|
| Easy       | Record an audio clip using Audio Recorder app and save it. | [View Demo](./video/AudioRecorderRecordAudio.mp4) |
| Medium     | Send a text message using Simple SMS Messenger to +15132327939 with message: The night is dark and full of terrors. | [View Demo](./video/SimpleSmsSend.mp4) |
| Hard       | In Simple Calendar Pro, create a calendar event on 2023-10-17 at 3h with the title 'Catch up on Annual Report' and the description 'We will prepare for software updates. Looking forward to productive discussions.'. The event should last for 60 mins. | [View Demo](./video/SimpleCalendarAddOneEvent.mp4) |

### Real-World Chinese Applications

| Scenario | User Instruction | Demo Link |
|----------|------------------|-----------|
| Video Playback | 打开b站，播放《孤独的美食家第10季》的第2集。 | [View Demo](./video/CNAPP_PlayVideo.mp4) |
| Ticket Ordering | 打开12306，购买5月20日北京出发到西安、最早一班的车票，其他要求：二等座、靠窗。 | [View Demo](./video/CNAPP_TicketOrder.mp4) |


## ✨ Technical Implementation

**Core Framework (jt_guiagent_v1)**

- `gui_agent_server.py` - FastAPI service layer
- `gui_agent.py` - Core agent framework  
- `model.py` - Model interface (proprietary)

**Evaluation Suite (androidworld_eval)**

- `agent_jt.py` - Evaluation script
- `result_info.pdf` - Task performance report
- `result_level.txt` - Capability metrics

## ✨ Roadmap & Improvements  

### Current Challenges
- ⏱️ Real-time execution latency
- 🔄 Complex task coordination
- 🖥️ Cross-platform compatibility

### Optimization Strategies

#### 1. Inference Acceleration
- ⚡ Parallel computing implementation
- ✂️ Model pruning & quantization
- 🏎️ Hardware-aware optimizations

#### 2. Lightweight Models
- 🎛️ Hyperparameter optimization
- 🧠 Advanced algorithm integration
- 📦 Knowledge distillation techniques

#### 3. Task Scheduling
- 📅 Efficient planning algorithms
- 🔄 Dynamic resource allocation
- 🧩 Modular task pipelining