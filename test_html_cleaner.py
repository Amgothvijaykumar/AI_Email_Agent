from bs4 import BeautifulSoup


def clean_email_html(html):
    """
    Convert HTML email content into clean readable text.
    """

    soup = BeautifulSoup(html, "html.parser")

    # Remove unwanted HTML sections
    for tag in soup(["script", "style", "head"]):
        tag.decompose()

    # Extract visible text
    text = soup.get_text(separator=" ")

    # Clean extra whitespace
    text = " ".join(text.split())

    return text


# Test HTML
html = """
<html>
<head>
    <style>
        body { color: red; }
    </style>
</head>

<body>
    <h1>Python Developer Job</h1>
    <p>We are looking for a Python developer intern.</p>
    <p>Location: Remote</p>

    <script>
        console.log("This should disappear");
    </script>
</body>
</html>
"""

cleaned = clean_email_html(html)

print("ORIGINAL HTML:")
print(html)

print("\n" + "=" * 60)

print("CLEAN TEXT:")
print(cleaned)