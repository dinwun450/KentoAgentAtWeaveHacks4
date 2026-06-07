import {
  CopilotRuntime,
  OpenAIAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { BuiltInAgent } from "@copilotkit/runtime/v2";
import { NextRequest } from "next/server";

const model = "gpt-4o-mini";
const serviceAdapter = new OpenAIAdapter({ model });
const runtime = new CopilotRuntime({
  agents: {
    default: new BuiltInAgent({ model: `openai/${model}` }),
  },
});

export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter,
    endpoint: "/api/copilotkit",
  });

  return handleRequest(req);
};
