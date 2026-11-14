import { redirect } from "next/navigation";

/** The landing route is the assistant itself once signed in. */
export default function Home() {
  redirect("/chat");
}
