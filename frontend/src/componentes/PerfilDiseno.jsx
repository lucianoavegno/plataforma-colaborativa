/**
 * Perfil de diseño de una instancia.
 *
 * Se muestran los cinco indicadores por separado y nunca un promedio: la
 * dificultad y la interdependencia son constructos distintos, y colapsarlos en
 * un puntaje único fue precisamente el defecto del esquema anterior.
 */
const INDICADORES = [
  {
    clave: 'interdependencia',
    sigla: 'IE',
    nombre: 'Interdependencia',
    ayuda: 'Qué parte de la ganancia alcanzable no logra ningún dato por separado.',
  },
  {
    clave: 'balance_carga',
    sigla: 'IBC',
    nombre: 'Balance de carga',
    ayuda: 'Qué tan parejo es el aporte de cada dato. 0 = una parte es un validador pasivo.',
  },
  {
    clave: 'emergencia',
    sigla: 'MEE',
    nombre: 'Emergencia',
    ayuda: 'Fracción de pasos que sólo existen como producto de la deducción conjunta.',
  },
  {
    clave: 'dificultad',
    sigla: 'DIF',
    nombre: 'Dificultad',
    ayuda: 'Cuánto falla el solver de referencia aun teniendo ambos datos.',
  },
];

export default function PerfilDiseno({ perfil, compacto = false }) {
  if (!perfil) {
    return (
      <p className={`sin-calibrar ${compacto ? 'compacto' : ''}`}>
        Sin calibrar con la configuración vigente
      </p>
    );
  }

  const cumple = perfil.interdependencia >= 0.8 && perfil.rondas_minimas >= 2;

  if (compacto) {
    return (
      <footer className="tarjeta-pie">
        <span className="indicador-compacto" title="Interdependencia epistémica">
          IE {perfil.interdependencia.toFixed(2)}
        </span>
        <span
          className={`indicador-compacto ${perfil.rondas_minimas < 2 ? 'alerta' : ''}`}
          title="Cota inferior de rondas de intercambio"
        >
          t<sub>mín</sub> {perfil.rondas_minimas}
        </span>
        <span className={`insignia ${cumple ? 'cumple' : 'no-cumple'}`}>
          {cumple ? 'cumple' : 'no cumple'}
        </span>
      </footer>
    );
  }

  return (
    <section className="panel-perfil">
      <header className="panel-perfil-encabezado">
        <h2>Perfil de diseño</h2>
        <span className={`insignia ${cumple ? 'cumple' : 'no-cumple'}`}>
          {cumple ? 'cumple el criterio' : 'no cumple el criterio'}
        </span>
      </header>

      <p className="nivel-texto">{perfil.nivel}</p>

      <div className="indicadores">
        {INDICADORES.map((ind) => (
          <div key={ind.clave} className="indicador" title={ind.ayuda}>
            <div className="indicador-fila">
              <span>
                <abbr>{ind.sigla}</abbr> {ind.nombre}
              </span>
              <strong>{perfil[ind.clave].toFixed(2)}</strong>
            </div>
            <div className="barra">
              <div
                className="barra-relleno"
                style={{ width: `${perfil[ind.clave] * 100}%` }}
              />
            </div>
          </div>
        ))}

        <div className="indicador" title="Cota inferior estructural de intercambios.">
          <div className="indicador-fila">
            <span>
              <abbr>t mín</abbr> Rondas mínimas
            </span>
            <strong className={perfil.rondas_minimas < 2 ? 'alerta' : ''}>
              {perfil.rondas_minimas}
            </strong>
          </div>
          {perfil.rondas_minimas < 2 && (
            <p className="nota-indicador">
              Se resuelve con un único intercambio: es un problema común partido en dos.
            </p>
          )}
        </div>
      </div>

      {perfil.monotonia_violada && (
        <p className="advertencia">
          Se violó la monotonía informacional: alguna celda con más datos acierta menos
          que una con menos. Revisar si el enunciado induce a error.
        </p>
      )}
    </section>
  );
}
