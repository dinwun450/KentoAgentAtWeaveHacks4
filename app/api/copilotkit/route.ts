import {
  CopilotRuntime,
  OpenAIAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
<<<<<<< HEAD
import { BuiltInAgent } from "@copilotkit/runtime/v2";
import { NextRequest } from "next/server";

const model = "gpt-4o-mini";
const serviceAdapter = new OpenAIAdapter({ model });
const runtime = new CopilotRuntime({
  agents: {
    default: new BuiltInAgent({ model: `openai/${model}` }),
  },
});
=======
import { NextRequest } from "next/server";

const serviceAdapter = new OpenAIAdapter({ model: "gpt-4o-mini" });
const runtime = new CopilotRuntime();
>>>>>>> 521a49b0e0a3ad6ce32510557931048dd1f7f57d

export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter,
    endpoint: "/api/copilotkit",
  });

  return handleRequest(req);
};
