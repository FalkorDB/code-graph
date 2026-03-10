import { useEffect } from "react";

const GoogleAnalytics = ({ ga_id }: { ga_id: string }) => {
  useEffect(() => {
    // Load gtag script
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${ga_id}`;
    document.head.appendChild(script);

    // Initialize gtag
    (window as any).dataLayer = (window as any).dataLayer || [];
    function gtag(...args: any[]) {
      (window as any).dataLayer.push(args);
    }
    gtag("js", new Date());
    gtag("config", ga_id);

    return () => {
      document.head.removeChild(script);
    };
  }, [ga_id]);

  return null;
};
export default GoogleAnalytics;