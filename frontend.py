import streamlit as st
from backend import chatbot, retrieve_all_threads
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import uuid


# ====================== Page Configuration ======================

st.set_page_config(
    page_title="Trip Planner AI",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================== Utilities ===========================
def generate_thread_id():
    return uuid.uuid4()

def reset_chat():
    thread_id = generate_thread_id()
    st.session_state["thread_id"] = thread_id
    add_thread(thread_id)
    st.session_state["message_history"] = []

def add_thread(thread_id):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)

def load_conversation(thread_id):
    state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
    # Check if messages key exists in state values, return empty list if not
    return state.values.get("messages", [])

# ======================= Session Initialization ===================
if "message_history" not in st.session_state:
    st.session_state["message_history"] = []

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = generate_thread_id()

if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"] = retrieve_all_threads()

add_thread(st.session_state["thread_id"])

# ============================ Sidebar ============================
st.sidebar.title("LangGraph Chatbot")

if st.sidebar.button("New Chat"):
    reset_chat()

st.sidebar.header("My Conversations")
for thread_id in st.session_state["chat_threads"][::-1]:
    if st.sidebar.button(str(thread_id)):
        st.session_state["thread_id"] = thread_id
        messages = load_conversation(thread_id)

        temp_messages = []
        for msg in messages:
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            temp_messages.append({"role": role, "content": msg.content})
        st.session_state["message_history"] = temp_messages

# ============================ Main UI ============================

# Render history
for message in st.session_state["message_history"]:
    with st.chat_message(message["role"]):
        st.text(message["content"])

user_input = st.chat_input("Type here")

if user_input:
    # Show user's message
    st.session_state["message_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.text(user_input)

    CONFIG = {
        "configurable": {"thread_id": st.session_state["thread_id"]},
        "metadata": {"thread_id": st.session_state["thread_id"]},
        "run_name": "chat_turn",
    }

    # Assistant streaming block
    with st.chat_message("assistant"):
        # Use a mutable holder so the generator can set/modify it
        status_holder = {"box": None, "logs": []}

        def ai_only_stream():
            for message_chunk, metadata in chatbot.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=CONFIG,
                stream_mode="messages",
            ):
                # Lazily create & update the SAME status container when any tool runs
                if isinstance(message_chunk, ToolMessage):
                    tool_name = getattr(message_chunk, "name", "tool")

                    # Extract tool call details
                    tool_input = getattr(message_chunk, "artifact", {})
                    if not tool_input:
                        # Try to get from additional_kwargs
                        tool_input = message_chunk.additional_kwargs.get("tool_input", {})

                    # Format tool log entry
                    log_entry = f"**{tool_name}**"
                    if tool_input:
                        # Format input parameters nicely
                        params = ", ".join([f"{k}={v}" for k, v in tool_input.items() if k and v])
                        if params:
                            log_entry += f"\n- Parameters: `{params}`"

                    # Add result summary if available
                    content = message_chunk.content
                    if content:
                        # Try to extract count/summary from result
                        if isinstance(content, str) and len(content) < 200:
                            log_entry += f"\n- Result: {content}"
                        elif isinstance(content, dict):
                            count = content.get("count", content.get("flights", content.get("hotels", content.get("attractions", content.get("videos", None)))))
                            if count:
                                log_entry += f"\n- Found: {count} results"

                    status_holder["logs"].append(log_entry)

                    if status_holder["box"] is None:
                        status_holder["box"] = st.status(
                            f"🔧 Using tools…", expanded=True
                        )

                    # Update status container with all logs
                    with status_holder["box"]:
                        st.markdown("### Tool Execution Log")
                        for i, log in enumerate(status_holder["logs"], 1):
                            st.markdown(f"{i}. {log}")

                # Stream ONLY assistant tokens
                if isinstance(message_chunk, AIMessage):
                    yield message_chunk.content

        ai_message = st.write_stream(ai_only_stream())

        # Finalize only if a tool was actually used
        if status_holder["box"] is not None:
            status_holder["box"].update(
                label=f"✅ Used {len(status_holder['logs'])} tool(s)",
                state="complete",
                expanded=False
            )

    # Save assistant message
    st.session_state["message_history"].append(
        {"role": "assistant", "content": ai_message}
    )