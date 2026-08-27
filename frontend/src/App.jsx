import { useState } from 'react';
import { useAuth } from './contexto-auth';
import Acceso from './componentes/Acceso';
import Catalogo from './componentes/Catalogo';
import VistaInstancia from './componentes/VistaInstancia';
import MisEpisodios from './componentes/MisEpisodios';
import PanelInvestigacion from './componentes/PanelInvestigacion';
import BarraEstado from './componentes/BarraEstado';

export default function App() {
  const { cuenta, cargando, salir, esInvestigador } = useAuth();
  const [vista, setVista] = useState('catalogo');
  const [instanciaId, setInstanciaId] = useState(null);

  if (cargando) return <div className="pantalla-carga">Cargando…</div>;
  if (!cuenta) return <Acceso />;

  function abrirInstancia(id) {
    setInstanciaId(id);
    setVista('instancia');
  }

  const enCatalogo = vista === 'catalogo' || vista === 'instancia';

  return (
    <div className="app">
      <header className="barra-superior">
        <button className="marca" onClick={() => setVista('catalogo')}>
          <span className="marca-sigla">CPS</span>
          <span className="marca-texto">Instrumento experimental</span>
        </button>

        <nav className="navegacion">
          <button className={enCatalogo ? 'activa' : ''} onClick={() => setVista('catalogo')}>
            Banco
          </button>
          <button
            className={vista === 'episodios' ? 'activa' : ''}
            onClick={() => setVista('episodios')}
          >
            Mis episodios
          </button>
          {esInvestigador && (
            <button
              className={vista === 'investigacion' ? 'activa' : ''}
              onClick={() => setVista('investigacion')}
            >
              Investigación
            </button>
          )}
        </nav>

        <div className="cuenta-actual">
          <span className="seudonimo" title="Identificador usado en la exportación">
            {cuenta.seudonimo}
          </span>
          {esInvestigador && <span className="etiqueta-rol">investigador</span>}
          <button className="boton-secundario" onClick={salir}>
            Salir
          </button>
        </div>
      </header>

      <BarraEstado />

      <main className="contenido">
        {vista === 'catalogo' && <Catalogo onAbrir={abrirInstancia} />}
        {vista === 'instancia' && instanciaId && (
          <VistaInstancia
            instanciaId={instanciaId}
            onVolver={() => setVista('catalogo')}
          />
        )}
        {vista === 'episodios' && <MisEpisodios onAbrirInstancia={abrirInstancia} />}
        {vista === 'investigacion' && esInvestigador && <PanelInvestigacion />}
      </main>
    </div>
  );
}
