export interface ToolInfo {
  name: string;
  description: string;
  category: string;
  /** True when the graph pauses for human approval before running it. */
  requires_approval: boolean;
}

export interface ToolListResponse {
  count: number;
  tools: ToolInfo[];
}
