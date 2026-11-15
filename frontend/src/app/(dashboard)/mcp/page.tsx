import { Plug } from "lucide-react";

import { ComingSoon } from "@/components/shared/coming-soon";

export default function McpPage() {
  return (
    <ComingSoon
      title="MCP servers"
      icon={<Plug className="size-4" />}
      summary="MCP lets the assistant use tools hosted by external servers."
      planned={[
        "Connecting to an MCP server",
        "Connection status and available tools per server",
        "Server configuration and credentials",
        "Disconnecting or removing a server",
      ]}
    />
  );
}
