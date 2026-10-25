// SAHL (سهل) brand mark — a rounded blue tile with the signature green dot and
// a white ring echoing the circle motif of the wordmark. Font-independent.
export default function Logo({ size = 40, className = '' }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={className}
         xmlns="http://www.w3.org/2000/svg" role="img" aria-label="SAHL">
      <rect width="64" height="64" rx="16" fill="#2254A4" />
      <circle cx="29" cy="35" r="13" fill="none" stroke="#ffffff" strokeWidth="5" />
      <circle cx="46" cy="20" r="7" fill="#4DBA7F" />
    </svg>
  );
}
