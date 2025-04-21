import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

def translate_code(source_code):
    prompt = f"Detect the programming language of the following code and translate it to another language as specified:\n\n{source_code}\n\nIf the source code is in Python, translate it to Java. If the source code is in Java, translate it to C++. Only output the translated code snippet as i have to give the translated code to another code file directly."
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt},
        ],
    )
    translated_code = response.choices[0].message.content.strip()
    return translated_code

