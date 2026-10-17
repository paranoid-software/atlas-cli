import {Plugster} from './plugster.js';
import {AtlasApi} from './atlas-api.js';
import {ShellPlugster} from './shell-plugster.js';

(async function() {
    let shellPlugster = await new ShellPlugster(new AtlasApi()).init();

    Plugster.plug(shellPlugster);
}());
