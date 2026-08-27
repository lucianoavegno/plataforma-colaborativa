import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('cps_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** Extrae un mensaje legible de un error de la API. */
export function mensajeDeError(error, porDefecto = 'Algo salió mal') {
  const detalle = error?.response?.data?.detail;
  if (typeof detalle === 'string') return detalle;
  if (Array.isArray(detalle) && detalle[0]?.msg) return detalle[0].msg;
  if (error?.message === 'Network Error') {
    return 'No se pudo contactar a la API. ¿Está corriendo en el puerto 8000?';
  }
  return porDefecto;
}

export const MODALIDADES = {
  agente_agente: 'Agente–agente',
  agente_estudiante: 'Agente–estudiante',
  resolucion_directa: 'Consulta de resolución',
};

export const ESTADOS = {
  en_curso: 'en curso',
  finalizado: 'finalizado',
  abandonado: 'abandonado',
};

export const VEREDICTOS = {
  correcto: 'correcto',
  incorrecto: 'incorrecto',
  no_parseable: 'no interpretable',
  sin_respuesta: 'sin respuesta',
};

export default api;
