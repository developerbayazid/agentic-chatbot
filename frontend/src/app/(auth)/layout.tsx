export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-dvh place-items-center px-4 py-10">
      {children}
    </div>
  );
}
