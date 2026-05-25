import OpenAI from "openai";

// BAD: hardcoded secret committed to source (should read from process.env)
export const openai = new OpenAI({
  apiKey: "sk-proj-9f3aXkQ2mZ7bL0pR8vN4tH1cD6eW5sY",
});

export const config = {
  model: "gpt-4o",
  maxRetries: 3,
};
