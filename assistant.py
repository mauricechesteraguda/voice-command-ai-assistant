import speech_recognition as sr

from ollama import Client

from gtts import gTTS

import os


client = Client(host="http://localhost:11434")
tempo_ratio = 1.3


def listen_for_command():
    recognizer = sr.Recognizer()

    with sr.Microphone() as source:
        print("Listening for command...")
        recognizer.adjust_for_ambient_noise(source)  # Adjust for ambient noise
        audio = recognizer.listen(source)

    try:
        print("Recognizing command...")
        command = recognizer.recognize_google(audio)
        print("You said:", command)
        return command
    except sr.UnknownValueError:
        print("Sorry, I didn't catch that. Please try again.")
        return None
    except sr.RequestError as e:
        print(
            "Could not request results from Google Speech Recognition service; {0}".format(
                e
            )
        )
        return None


system_message = "You are a helpful AI assistant. Make your answers to my queries short but very informative as much as possible especially if i am not asking about codes. If the user stated a much shorter response, do it. Now my query is "


def process_command(command):
    response = client.chat(
        model="llama2:7b",
        messages=[
            {
                "role": "user",
                "content": system_message + command,
            },
        ],
    )
    print(response["message"]["content"])
    speak(response["message"]["content"])


def speak(text):
    tts = gTTS(text, slow=False)
    tts.save("speech.mp3")
    os.system("mplayer -af scaletempo -speed 1.5 speech.mp3")


if __name__ == "__main__":
    while True:
        command = listen_for_command()
        if command and command.lower() == "exit":
            print("Exiting...")
            break
        elif command:
            process_command(command)
