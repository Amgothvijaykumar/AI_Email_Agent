from semantic_search_tool import search_emails_semantically


query = input("Search emails: ")

result = search_emails_semantically.invoke({
    "query": query
})

print("\nRESULT:")
print(result)