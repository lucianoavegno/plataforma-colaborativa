import { createContext, useContext } from 'react';

/**
 * Contexto de sesión.
 *
 * Vive en su propio módulo, separado del proveedor, porque un archivo que
 * exporta componentes y valores a la vez rompe el refresco en caliente durante
 * el desarrollo.
 */
export const ContextoAuth = createContext(null);

export function useAuth() {
  const ctx = useContext(ContextoAuth);
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>');
  return ctx;
}
