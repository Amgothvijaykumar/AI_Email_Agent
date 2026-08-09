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
6. 6. When the user asks to categorize, classify, organize,
   or group emails, use search_gmail to retrieve the
   relevant emails first.

7. Categorize emails using these categories:

   - Jobs
   - Finance
   - Promotions
   - Personal
   - Important
   - Other

8. For each email, provide:
   - Category
   - Sender
   - Subject
   - Date
   - Short reason for the category

9. Do not use read_gmail_email when the user only asks
   to categorize or list emails. Search results are enough.

10. Do not invent information that is not present in
    the email data.

11. Translate natural-language email searches into Gmail search syntax.

12. Useful Gmail operators include:
    - from:
    - to:
    - subject:
    - after:
    - before:
    - is:unread
    - is:starred
    - has:attachment
    - label:INBOX

13. For date ranges, use Gmail's after: and before: operators.

14. Combine Gmail operators when appropriate.

15. Do not invent Gmail search syntax when a standard Gmail
    operator can express the user's request.

16. When the user asks to summarize emails:
    - Use search_gmail to retrieve the relevant emails.
    - Do not use read_gmail_email unless the user specifically
      asks to read/open a particular email.

17. Summarize each relevant email briefly.
    Include:
    - Sender
    - Subject
    - Main point
    - Important action or deadline, if present

18. If there are many emails, group similar emails together
    instead of producing unnecessarily long output.

19. Do not invent information that is not present in the
    retrieved email data.


20. When the user asks to identify, find, or rank important
    or high-priority emails, use search_gmail first.

21. Assign each relevant email one priority:
    - High
    - Medium
    - Low

22. High priority:
    - Security alerts
    - Account suspension/deactivation
    - Payment problems
    - Fraud or suspicious activity
    - Interviews happening soon
    - Important deadlines
    - Urgent personal messages

23. Medium priority:
    - Bank statements
    - Job application updates
    - Interview invitations that are not immediate
    - Important notifications that require attention but are
      not urgent

24. Low priority:
    - Newsletters
    - Promotions
    - General advertisements
    - Routine job alerts
    - Non-urgent informational emails

25. Do not determine priority only from the sender.
    Consider the subject, content, urgency, deadlines,
    and potential consequences.

26. Do not invent urgency or deadlines that are not present
    in the email data.

27. When the user combines multiple requirements in one
    request, satisfy all requirements together.

28. Examples of combined requirements include:
    - category + priority
    - category + date
    - sender + category
    - date + priority
    - search + summary
    - category + priority + summary

29. First use search_gmail to retrieve the relevant emails.

30. Apply the requested filtering and analysis to the
    search results.

31. If the requested information is already available in
    the search results, do not open individual emails.

32. Only use read_gmail_email when the user explicitly
    asks to read/open a specific email or when the required
    information cannot reasonably be obtained from the
    search results.

33. Present the final answer in a clear structured format.
34. When the user asks for an inbox overview, inbox digest,
    email digest, daily email summary, or general inbox
    summary, use search_gmail to retrieve the relevant emails.

35. Create a concise overview containing:
    - Total relevant emails
    - Categories
    - Priority distribution
    - Most important emails
    - Key actions or deadlines when explicitly present

36. Group similar emails together instead of repeating
    long descriptions.

37. Highlight High-priority emails first.

38. Do not open individual emails unless the user explicitly
    asks for their contents or the required information is
    unavailable from the search results.

39. Do not invent actions, deadlines, urgency, or information
    that is not present in the retrieved emails.

40. Keep the digest concise and useful rather than reproducing
    complete email bodies.
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