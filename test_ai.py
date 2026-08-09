from email_ai import analyze_email


result = analyze_email(
    sender="Indeed <donotreply@jobalert.indeed.com>",
    subject="Python Developer Jobs",
    body="""
    Indeed Job Alert

    19 new Python developer jobs are available.
    Many of these jobs are remote.
    """
)

print("\nAI ANALYSIS")
print("=" * 50)
print(result)