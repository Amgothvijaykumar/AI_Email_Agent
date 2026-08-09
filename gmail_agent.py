import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage
)

from gmail_tools import (
    search_gmail,
    read_gmail_email
)


# --------------------------------------------------
# 1. Gemini API key
# --------------------------------------------------

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY not found."
    )


# --------------------------------------------------
# 2. Create Gemini model
# --------------------------------------------------

llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    google_api_key=api_key,
    temperature=0
)


# --------------------------------------------------
# 3. Register Gmail tools
# --------------------------------------------------

tools = [
    search_gmail,
    read_gmail_email
]

llm_with_tools = llm.bind_tools(tools)


# --------------------------------------------------
# 4. Conversation memory
# --------------------------------------------------

messages = [
    SystemMessage(
        content="""
You are a Gmail assistant.

Follow these rules carefully:

1. If the user asks to FIND, SEARCH, LIST, SHOW, or LOOK FOR emails:
   - Use search_gmail.
   - Do NOT use read_gmail_email unless the user explicitly asks
     to open, read, inspect, or summarize a specific email.

2. If the user asks to OPEN or READ a specific email:
   - First use search_gmail if you need to identify the email.
   - Use the exact Email ID returned by search_gmail.
   - Then use read_gmail_email.

3. Never use an email subject, sender name, or keyword as a message_id.
   A message_id must be the exact Email ID returned by search_gmail.

4. If the user only asks for a list of emails, do not open every email.

5. Answer the user directly and concisely.
"""
    )
]


# --------------------------------------------------
# 5. Continuous conversation
# --------------------------------------------------

while True:

    question = input(
        "\nAsk your Gmail agent: "
    )

    # Exit command
    if question.lower() in [
        "exit",
        "quit",
        "bye"
    ]:

        print(
            "\nGmail agent stopped."
        )

        break


    # Add user's message
    messages.append(
        HumanMessage(
            content=question
        )
    )


    # --------------------------------------------------
    # 6. Agent tool loop
    # --------------------------------------------------

    while True:

        response = llm_with_tools.invoke(
            messages
        )

        # Add Gemini response
        messages.append(
            response
        )


        # --------------------------------------------------
        # 7. No tool call = final answer
        # --------------------------------------------------

        if not response.tool_calls:

            content = response.content

            if isinstance(content, list):
                print("\nAI:", content[0]["text"])
            else:
                print("\nAI:", content)

            break


        # --------------------------------------------------
        # 8. Execute requested tools
        # --------------------------------------------------

        for tool_call in response.tool_calls:

            tool_name = tool_call["name"]

            tool_args = tool_call["args"]


            print(
                f"\n🔧 Using tool: {tool_name}"
            )

            print(
                f"Arguments: {tool_args}"
            )


            # Search Gmail
            if tool_name == "search_gmail":

                result = search_gmail.invoke(
                    tool_args
                )


            # Read Gmail email
            elif tool_name == "read_gmail_email":

                result = read_gmail_email.invoke(
                    tool_args
                )


            else:

                result = (
                    f"Unknown tool: {tool_name}"
                )


            # --------------------------------------------------
            # 9. Send tool result back to Gemini
            # --------------------------------------------------

            messages.append(
                ToolMessage(
                    content=result,
                    tool_call_id=tool_call["id"]
                )
            )