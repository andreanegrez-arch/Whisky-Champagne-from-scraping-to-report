import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const tunnelFilePath = path.join(__dirname, 'tunnel.txt');

function startTunnel() {
  console.log('🔄 Avvio Tunnel Sicuro Globale...');

  // Usa l'SSH integrato in Windows per creare un tunnel stabile gratuito
  const ssh = spawn('ssh', [
    '-R', '80:localhost:3000',
    '-o', 'StrictHostKeyChecking=accept-new',
    'nokey@localhost.run'
  ]);

  const handleData = (data) => {
    const output = data.toString();
    
    // Mostriamo i log nascondendo eventuali QR code giganti del server
    if (!output.includes('QR')) {
        process.stdout.write(output);
    }
    
    // Cerca il link generato (formato https://xyz.lhr.life)
    const match = output.match(/https:\/\/[a-zA-Z0-9.-]+\.lhr\.(life|dev|app|net)/);
    if (match) {
        const url = match[0];
        console.log(`\n======================================================`);
        console.log(`🌐 TUNNEL GLOBALE ATTIVO: ${url}`);
        console.log(`======================================================\n`);
        fs.writeFileSync(tunnelFilePath, url);
    }
  };

  ssh.stdout.on('data', handleData);
  ssh.stderr.on('data', handleData);

  ssh.on('close', (code) => {
    console.log(`\n🛑 Tunnel disconnesso dai server. Riconnessione tra 5 secondi...`);
    if (fs.existsSync(tunnelFilePath)) fs.unlinkSync(tunnelFilePath);
    setTimeout(startTunnel, 5000);
  });
}

// Pulisci il file alla chiusura
process.on('SIGINT', () => {
  if (fs.existsSync(tunnelFilePath)) fs.unlinkSync(tunnelFilePath);
  process.exit();
});

// Avvia l'infrastruttura
startTunnel();
