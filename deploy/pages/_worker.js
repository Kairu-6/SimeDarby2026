// Cloudflare Pages advanced-mode worker: same-origin API for the Expo web export.
// Python + PyTorch run on the separate API host. No device key is shipped here.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/api/')) return env.ASSETS.fetch(request);
    if (url.pathname.startsWith('/api/device/')) {
      return Response.json({ detail: 'Hardware connects directly to the private Python API.' }, { status: 404 });
    }
    const origin = env.API_ORIGIN;
    if (!origin) return Response.json({ detail: 'The API host has not been configured for this preview.' }, { status: 503 });
    let target;
    try {
      target = new URL(origin);
      if (target.protocol !== 'https:' || target.username || target.password || target.pathname !== '/') throw new Error('Invalid origin');
    } catch {
      return Response.json({ detail: 'The API host configuration is invalid.' }, { status: 503 });
    }
    target.pathname = url.pathname;
    target.search = url.search;
    const headers = new Headers(request.headers);
    headers.delete('host');
    headers.delete('cookie');
    headers.delete('x-device-key');
    headers.delete('x-device-id');
    headers.delete('x-forwarded-host');
    headers.delete('x-forwarded-proto');
    try {
      const response = await fetch(target, {
        method: request.method, headers,
        body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
        redirect: 'manual',
        signal: AbortSignal.timeout(url.pathname.includes('/vision/') ? 125000 : 20000),
      });
      const resultHeaders = new Headers(response.headers);
      resultHeaders.set('Cache-Control', 'no-store');
      resultHeaders.set('X-Content-Type-Options', 'nosniff');
      resultHeaders.delete('Set-Cookie');
      return new Response(response.body, { status: response.status, headers: resultHeaders });
    } catch {
      return Response.json({ detail: 'The bin service is currently unreachable. Please retry shortly.' }, { status: 502 });
    }
  },
};
