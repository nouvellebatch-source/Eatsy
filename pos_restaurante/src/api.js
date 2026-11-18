export const base = (import.meta.env.VITE_EATSY_API_URL || 'https://eatsy-1.onrender.com').replace(/\/$/, '');
export async function request(path, {token, timeoutMs = 60000, ...options} = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(base + path, { ...options, signal: controller.signal,
      headers: {Accept:'application/json', ...(options.body ? {'Content-Type':'application/json'} : {}),
        ...(token ? {Authorization:`Bearer ${token}`} : {}), ...options.headers}});
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'No fue posible completar la solicitud.');
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('La API tardó demasiado en responder.');
    if (error instanceof TypeError) throw new Error('No se pudo conectar con la API. Revisa la conexión y el origen permitido.');
    throw error;
  } finally { clearTimeout(timeout); }
}
export const nextStatus = {pending_acceptance:'confirmed',confirmed:'preparing',preparing:'cooked',cooked:'ready',ready:'delivered'};
export const labels = {pending_acceptance:'Por confirmar',confirmed:'Confirmado',preparing:'En preparación',cooked:'Cocinado',ready:'Listo',delivered:'Entregado'};
