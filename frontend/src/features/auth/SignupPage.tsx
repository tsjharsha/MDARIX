// The free trial request page (/signup), a website page: pre-rendered at build time (site/prerender.tsx) and loaded
// with the website, so it is drawn at once (WEB-05, WEB-06). The other account pages are AuthPage.tsx.
import { AuthFrame } from "./AuthFrame";
import { SignupForm } from "./SignupForm";

export function SignupPage() {
  return (
    <AuthFrame mode="signup">
      <SignupForm />
    </AuthFrame>
  );
}
