### Currently support Linux for now

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
