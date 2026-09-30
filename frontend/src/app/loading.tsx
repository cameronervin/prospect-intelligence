import { typeStyles } from "@/components/ui/styles";

export default function Loading() {
  return (
    <p role="status" className={`${typeStyles.utility} px-4 py-6 sm:px-6 lg:px-8`}>
      Loading workspace…
    </p>
  );
}
