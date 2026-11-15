import { Puzzle } from "lucide-react";

import { ComingSoon } from "@/components/shared/coming-soon";

export default function PluginsPage() {
  return (
    <ComingSoon
      title="Plugins"
      icon={<Puzzle className="size-4" />}
      summary="Plugins let an installation add new tools and integrations."
      planned={[
        "Browsing and installing plugins",
        "Enabling or disabling a plugin",
        "Per-plugin configuration",
        "Status and health for each installed plugin",
      ]}
    />
  );
}
