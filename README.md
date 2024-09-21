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


Usage

    Run the main Python file:

    bash

python assistant.py

The application will start listening for voice commands. Speak your command into your microphone. Example commands:

    "What's the weather today?"
    "Explain artificial intelligence."
    "Stop now" (to stop the assistant from talking).

To exit the application, simply say:

bash

    exit

How It Works

    The assistant listens for commands through the microphone using the speech_recognition library.
    Once a command is captured, it sends the query to the LLaMA model via the ollama client.
    The assistant converts the AI-generated response into speech using gTTS.
    Speech is played back using mplayer at an increased speed (adjustable via the tempo_ratio).

Cancelling Responses

You can interrupt the assistant while it is speaking by saying commands like:

    "Stop now"
    "Shut up"
    "End now"
    "Terminate now"

The assistant will stop speaking and cancel any further responses.
Project Structure

plaintext

.
├── app.py                 # Main Python script for the assistant
├── README.md              # Project documentation
├── requirements.txt       # Python dependencies
└── speeches/              # Directory where generated speech files are stored

Dependencies

    Google Speech Recognition
    gTTS
    psutil
    mplayer
    Ollama Client (For LLaMA model inference)

You can install these dependencies using the following command:

bash

pip install -r requirements.txt

Acknowledgments

    Google Speech Recognition for the speech-to-text functionality.
    Google Text-to-Speech (gTTS) for converting text responses to audio.
    LLaMA AI Model for generating intelligent responses.

License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0) License. See the LICENSE file for details.