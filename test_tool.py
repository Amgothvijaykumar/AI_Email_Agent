from gmail_tools import search_gmail


result = search_gmail.invoke(
    {
        "query": "subject:job"
    }
)

print(result)