export function Logo() {
  return (
    <svg
      width="32"
      height="32"
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="text-primary"
    >
      <rect width="32" height="32" rx="8" fill="currentColor" />
      <path
        d="M9 23V9H12.5L16 16L19.5 9H23V23H20V12L16.5 19H15.5L12 12V23H9Z"
        fill="hsl(var(--primary-foreground))"
      />
    </svg>
  );
}
