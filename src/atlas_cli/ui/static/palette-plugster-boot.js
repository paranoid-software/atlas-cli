import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {PalettePlugster} from './palette-plugster.js';

(async function() {
    let palettePlugster = await new PalettePlugster(new AtlasApi()).init();

    Plugster.plug(palettePlugster);
}());
