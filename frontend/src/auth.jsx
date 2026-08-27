import { useCallback, useEffect, useState } from 'react';
import api from './api';
import { ContextoAuth } from './contexto-auth';

const CLAVE_TOKEN = 'cps_token';

export function AuthProvider({ children }) {
  const [cuenta, setCuenta] = useState(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem(CLAVE_TOKEN);
    if (!token) {
      setCargando(false);
      return;
    }
    api
      .get('/api/auth/yo')
      .then((r) => setCuenta(r.data))
      .catch(() => localStorage.removeItem(CLAVE_TOKEN))
      .finally(() => setCargando(false));
  }, []);

  const guardar = useCallback((datos) => {
    localStorage.setItem(CLAVE_TOKEN, datos.access_token);
    setCuenta(datos.cuenta);
  }, []);

  const ingresar = useCallback(
    async (email, password) => {
      const { data } = await api.post('/api/auth/login', { email, password });
      guardar(data);
    },
    [guardar],
  );

  // El consentimiento no es una casilla de perfil: se envía con el registro y
  // el backend lo asienta con la versión y el hash del texto aceptado.
  const registrar = useCallback(
    async (nombre, email, password) => {
      const { data } = await api.post('/api/auth/registro', {
        nombre,
        email,
        password,
        acepta_consentimiento: true,
      });
      guardar(data);
    },
    [guardar],
  );

  const salir = useCallback(() => {
    localStorage.removeItem(CLAVE_TOKEN);
    setCuenta(null);
  }, []);

  const esInvestigador = cuenta?.rol === 'investigador';

  return (
    <ContextoAuth.Provider
      value={{ cuenta, cargando, ingresar, registrar, salir, esInvestigador }}
    >
      {children}
    </ContextoAuth.Provider>
  );
}
