import { useEffect, useState } from 'react';
import { useAuth } from '../contexto-auth';
import api, { mensajeDeError } from '../api';

/**
 * Ingreso y alta de cuenta.
 *
 * El alta exige leer y aceptar el consentimiento informado. El texto se trae de
 * la API en lugar de estar duplicado acá: el backend registra qué versión aceptó
 * cada persona, así que la que se muestra tiene que ser exactamente esa.
 */
export default function Acceso() {
  const { ingresar, registrar } = useAuth();
  const [modo, setModo] = useState('ingreso');
  const [nombre, setNombre] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [acepta, setAcepta] = useState(false);
  const [consentimiento, setConsentimiento] = useState(null);
  const [error, setError] = useState('');
  const [enviando, setEnviando] = useState(false);

  const esAlta = modo === 'alta';

  useEffect(() => {
    if (!esAlta || consentimiento) return;
    api
      .get('/api/auth/consentimiento')
      .then((r) => setConsentimiento(r.data))
      .catch(() => setConsentimiento(null));
  }, [esAlta, consentimiento]);

  async function enviar(evento) {
    evento.preventDefault();
    setError('');
    setEnviando(true);
    try {
      if (esAlta) await registrar(nombre, email, password);
      else await ingresar(email, password);
    } catch (e) {
      setError(mensajeDeError(e, 'No se pudo completar la operación'));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="acceso">
      <div className="acceso-panel">
        <p className="acceso-sigla">CPS</p>
        <h1 className="acceso-titulo">
          Estudio sobre resolución colaborativa de problemas
        </h1>
        <p className="acceso-bajada">
          Problemas de matemática repartidos entre dos participantes: cada parte tiene un
          dato que la otra necesita y ninguna alcanza la solución por separado.
        </p>

        <div className="pestanas">
          <button
            type="button"
            className={!esAlta ? 'activa' : ''}
            onClick={() => {
              setModo('ingreso');
              setError('');
            }}
          >
            Ingresar
          </button>
          <button
            type="button"
            className={esAlta ? 'activa' : ''}
            onClick={() => {
              setModo('alta');
              setError('');
            }}
          >
            Participar
          </button>
        </div>

        <form onSubmit={enviar} className="formulario">
          {esAlta && (
            <label>
              Nombre
              <input
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                required
                autoComplete="name"
              />
            </label>
          )}
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </label>
          <label>
            Contraseña
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete={esAlta ? 'new-password' : 'current-password'}
            />
            {esAlta && <span className="ayuda">Mínimo 8 caracteres.</span>}
          </label>

          {esAlta && (
            <section className="consentimiento">
              <h2>
                Consentimiento informado
                {consentimiento && (
                  <span className="version">versión {consentimiento.version}</span>
                )}
              </h2>
              <div className="consentimiento-cuerpo">
                {consentimiento ? (
                  consentimiento.cuerpo
                    .split('\n\n')
                    .map((parrafo, indice) => <p key={indice}>{parrafo}</p>)
                ) : (
                  <p className="cargando">Cargando el texto…</p>
                )}
              </div>
              <label className="casilla">
                <input
                  type="checkbox"
                  checked={acepta}
                  onChange={(e) => setAcepta(e.target.checked)}
                />
                <span>Leí y acepto participar en estas condiciones.</span>
              </label>
            </section>
          )}

          {error && <p className="error">{error}</p>}

          <button
            type="submit"
            className="boton-principal"
            disabled={enviando || (esAlta && (!acepta || !consentimiento))}
          >
            {enviando ? 'Procesando…' : esAlta ? 'Crear cuenta y participar' : 'Ingresar'}
          </button>
        </form>

        <p className="nota-pie">
          Tus datos se guardan asociados a un seudónimo. Podés retirar el consentimiento
          en cualquier momento y pedir que se borren tus episodios.
        </p>
      </div>
    </div>
  );
}
