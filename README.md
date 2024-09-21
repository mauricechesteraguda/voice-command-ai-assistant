### Currently support Linux for now

# Voice Command AI Assistant

This project is a voice-activated AI assistant that listens to voice commands, processes them using a large language model, and responds with synthesized speech. The AI assistant can handle natural language queries and generate helpful responses in real time. It includes the ability to interrupt and stop ongoing responses, as well as adjustable speech playback speed.

## Features
- **Voice Recognition**: Listens for voice commands using Google Speech Recognition.
- **AI-Powered Responses**: Uses a local instance of the LLaMA model to generate responses based on the user's queries.
- **Speech Synthesis**: Converts the AI response to speech using Google Text-to-Speech (gTTS).
- **Real-Time Interaction**: Responds to commands as they are given, with the ability to cancel or stop ongoing responses.
- **Multi-process handling**: Commands are processed in parallel with the help of Python’s `multiprocessing` module.

## Prerequisites
Before running the project, ensure you have the following installed on your system:
- Python 3.8 or higher
- Required Python packages (listed in the requirements section below)
- [Google Speech Recognition API](https://pypi.org/project/SpeechRecognition/)
- [gTTS (Google Text-to-Speech)](https://pypi.org/project/gTTS/)
- [psutil](https://pypi.org/project/psutil/)
- [mplayer](http://www.mplayerhq.hu/) (for speech playback)

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/mauricechesteraguda/voice-command-ai-assistant.git
   cd voice-command-ai-assistant
    ```


2. Install the required Python packages:

    ```bash
    pip install -r requirements.txt
    ```
    
3. Ensure that mplayer is installed on your system. For Linux, you can install it with:
    ```bash
    sudo apt-get install mplayer
    ```

4. Set up the ollama client to run LLaMA locally. You can find more about the installation here: https://ollama.com/.


0. Install ollama

`curl -fsSL https://ollama.com/install.sh | sh`

`ollama run llama2:7b`

1. Make sure to install mplayer

`sudo apt install mplayer`

2. Install python 3.11

3. Install virtualenv

4. create a virtual environment

`virtualenv -p python3 .venv`

5. Execute this to enable the virtual environment

`source .venv/bin/activate`

6. Install the dependencies

`pip install -r requirements.txt`

7. Run the app

`python assistant.py`
