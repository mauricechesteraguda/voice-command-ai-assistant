import time
import speech_recognition as sr

from ollama import Client

from gtts import gTTS

import os

import re

import threading

global is_talking
is_talking = False


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


def queue_message(command):
    # Regular expression pattern to match sentence endings (. ! ?)
    sentence_endings = r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|!)\s"
    sentences = re.split(sentence_endings, command)
    # Remove any empty strings in the list
    sentences = [sentence.strip() for sentence in sentences if sentence.strip() != ""]
    return sentences


def process_command(command):
    global is_talking
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

    sentences = queue_message(response["message"]["content"])

    i = 0
    while i < len(sentences):
        m = sentences[i]
        generate_speech(m, i, sentences)
        i += 1

    is_talking = False


def generate_speech(text, i, sentences):
    global is_talking
    tts = gTTS(text, slow=False)
    tts.save("speech" + str(i) + ".mp3")
    if not is_talking:
        # Create a new thread to run the play_audio function
        audio_thread = threading.Thread(target=speak, args=(len(sentences),))
        audio_thread.start()  # Start the thread

        is_talking = True


def speak(num_sentences):
    time.sleep(2)
    # os.system("mplayer -af scaletempo -speed 1.3 speech" + str(i) + ".mp3")
    for i in range(num_sentences):
        os.system(f"mplayer -af scaletempo -speed 1.3 speech{i}.mp3")


if __name__ == "__main__":
    while True:
        command = listen_for_command()
        if command and command.lower() == "exit":
            print("Exiting...")
            break
        elif command:
            process_command(command)
