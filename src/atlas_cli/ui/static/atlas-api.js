// The page's only way to the Atlas: the read-only JSON endpoints `atlas ui` serves.
export class AtlasApi {
    get(name) {
        return $.ajax({url: `/api/${name}`, dataType: 'json', cache: false});
    }
}
