import { generateText, streamText } from "ai";
import { createAnthropic } from "@ai-sdk/anthropic";

export async function resolveTicket(conversationId, customerId) {
  const model = createAnthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const result = await generateText({ model, prompt: "resolve" });
  ticket.status = "resolved";
  await ticket.save();
  return result;
}

export async function chargeCustomer(customerId) {
  await stripe.charges.create({ amount: 100 });
  return streamText({ prompt: "charge" });
}

export async function notifyViaSalesforce(applicationId) {
  await salesforce.leads.update({ id: applicationId });
}
