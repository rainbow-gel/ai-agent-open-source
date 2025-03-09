# app.py
import json
import streamlit as st
import requests

from typing_extensions import override
from openai import OpenAI
from openai import AssistantEventHandler
from openai.types.beta.assistant_stream_event import ThreadMessageDelta
from openai.types.beta.threads.text_delta_block import TextDeltaBlock

# ----------------------------------------------------------------------
# 1) Define your tool/function
# ----------------------------------------------------------------------
def fuel_calculator(weight, distance, duration, gender=None):
    print(f"weight: {weight}, distance: {distance}, duration: {duration}, gender: {gender}")
    url = "https://sportstech.maurten.com/v1/simulationResults"
    API_KEY_PROD=str(st.secrets["MAURTEN_API_KEY"])

    headers = {
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key" : API_KEY_PROD
        }
    
    with open("examples/userInput.json", "r") as file:
        input_json = json.load(file)
    input_json["data"]["weight"] = weight
    input_json["data"]["environment"]["raceData"]["distance"] = distance
    input_json["data"]["environment"]["raceData"]["duration"] = duration
    if gender:
        input_json["data"]["gender"] = gender

    try:
        response = requests.post(url, json=input_json, headers=headers)
        outputJson = response.json()
        status = response.status_code
        # print(f" version: {outputJson['version']}")
        if status == 200:
            output = ""
            warmup_product = outputJson["data"]["fuelingProtocol"]["warmUp"]["details"][0]["product"]
            output += f"You should intake a {warmup_product} during warmup, roughly 30 minutes before start.\n"
            for prod in outputJson["data"]["fuelingProtocol"]["duringRace"]["details"]:
                output += f"Take a {prod['product']} at {prod['timing']} km.\n"
            hourly_intake = outputJson["data"]["scalarValues"]["carbsPerHour"]
            output += f"Giving you an hourly intake of {hourly_intake} grams of carbs."
            print(output)
            return output
        else:
            print(f"Error: {output}")
            return "Sorry the fuel calculator is not available at the moment."
    except Exception as e:
        print(f"Error: {e}")
        return "Sorry the fuel calculator is not available at the moment."
    

# ----------------------------------------------------------------------
# 2) Create a subclass of AssistantEventHandler to handle tool calls and text updates
# ----------------------------------------------------------------------
class MyEventHandler(AssistantEventHandler):
    def __init__(self, reply_box, reply_container):
        super().__init__()
        self.reply_box = reply_box
        self.reply_container = reply_container  # Mutable container for text

    @override
    def on_event(self, event):
        if event.event == "thread.run.requires_action":
            self.handle_requires_action(event.data, event.data.id)

    @override
    def on_text_delta(self, delta, snapshot):

        # Update the reply container and UI on each text delta
        self.reply_container['text'] += delta.value
        self.reply_box.markdown(self.reply_container['text'])

    def handle_requires_action(self, data, run_id):
        tool_outputs = []
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            if tool.function.name == "fuel_calculator":
                args_dict = json.loads(tool.function.arguments)
                weight = args_dict.get("weight", 0)
                distance = args_dict.get("distance", 0)
                duration = args_dict.get("duration", 0)
                gender = args_dict.get("gender", 0)
                # print(f"insdie tool call handler: weight: {weight}, distance: {distance}, duration: {duration}")
                carbs_recommendation = fuel_calculator(weight, distance, duration, gender)
                tool_outputs.append({"tool_call_id": tool.id, "output": carbs_recommendation})

        self.submit_tool_outputs(tool_outputs, run_id)

    def submit_tool_outputs(self, tool_outputs, run_id):
        # Submit tool outputs and reuse the same reply_box and container
        with client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=self.current_run.thread_id,
            run_id=self.current_run.id,
            tool_outputs=tool_outputs,
            event_handler=MyEventHandler(self.reply_box, self.reply_container),
        ) as stream:
            for _ in stream:
                pass  # Let the event handler process the text deltas

# ----------------------------------------------------------------------
# 3) Initialize your OpenAI client and retrieve the assistant
# ----------------------------------------------------------------------
client = OpenAI()
assistant_id = "asst_t9geBhYxVy4sXjK6qqK0aonh"  # Replace with your assistant ID
assistant = client.beta.assistants.retrieve(assistant_id)

# ----------------------------------------------------------------------
# 4) Streamlit UI
# ----------------------------------------------------------------------
st.title("Demo: OpenAI Assistants API + Tool Calls")
pw_match = 'show-me-the-hydrogel'
if st.text_input("Enter password", type="password") == pw_match:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "thread_id" not in st.session_state:
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_query := st.chat_input("Ask me a question..."):
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state.chat_history.append({"role": "user", "content": user_query})

        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=user_query
        )

        with st.chat_message("assistant"):
            assistant_reply_box = st.empty()
            assistant_reply_container = {'text': ''}  # Holds the accumulated text

            event_handler = MyEventHandler(assistant_reply_box, assistant_reply_container)

            with client.beta.threads.runs.stream(
                thread_id=st.session_state.thread_id,
                assistant_id=assistant_id,
                event_handler=event_handler,
            ) as stream:
                for _ in stream:
                    pass  # Event handler processes all events

            st.session_state.chat_history.append(
                {"role": "assistant", "content": assistant_reply_container['text']}
            )