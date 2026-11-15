import { Blocks } from "lucide-react";

import { ComingSoon } from "@/components/shared/coming-soon";

export default function SkillsPage() {
  return (
    <ComingSoon
      title="Skills"
      icon={<Blocks className="size-4" />}
      summary="Skills are reusable, packaged instructions an agent can load on demand."
      planned={[
        "Installing and removing skills",
        "Descriptions and status for each installed skill",
        "Activating a skill for a conversation or session",
        "Managing skill versions and updates",
      ]}
    />
  );
}
