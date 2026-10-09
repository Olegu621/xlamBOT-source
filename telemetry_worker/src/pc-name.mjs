export function cleanPCName(value = '') {
  if (typeof value !== 'string' || [...value].length > 64 || /\p{C}/u.test(value)) throw Error('invalid_pc_name');
  return value.trim();
}
export async function savePCName(db, installation, name) {
  await db.prepare('INSERT INTO installation_names VALUES(?,?) ON CONFLICT(installation) DO UPDATE SET name=excluded.name').bind(installation, cleanPCName(name)).run();
}
