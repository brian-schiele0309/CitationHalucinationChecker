from openai import OpenAI

endpoint = "endpoint_goes_here"
deployment_name = "DeepSeek-V3.1"
api_key = "api_key_goes_here"

client = OpenAI(
    base_url=endpoint,
    api_key=api_key
)

completion = client.chat.completions.create(
    model=deployment_name,
    messages=[
        {
            "role": "user",
            "content": "What is the capital of France?",
        }
    ],
    temperature=0.7,
)

print(completion.choices[0].message)
