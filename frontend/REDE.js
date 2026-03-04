let trackingCode = "";
let statusInterval;
let currentUserRole = "user";

const statusMap = {
  received: { value: 10, text: "Arquivo recebido" },
  preparing: { value: 20, text: "Lendo arquivo" },
  uploading: { value: 30, text: "Enviando arquivo para processamento..." },
  question_answering: { value: 40, text: "Respondendo perguntas..." },
  summarizing: { value: 60, text: "Gerando resumo..." },
  generating_pdf: { value: 80, text: "Gerando PDF..." },
  zipping: { value: 90, text: "Compactando arquivos..." },
  finished: { value: 100, text: "Processamento finalizado!" },
  error: { value: 0, text: "Erro no processamento." },
  cancelled: { value: 0, text: "Processamento cancelado pelo usuário." }
};

document.addEventListener('DOMContentLoaded', function() {
    const token = localStorage.getItem('accessToken');
    if (!token) {
        window.location.href = '/login';
        return;
    }
    
    initializeDarkMode();
    
    fetch('/users/me', {
        headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(response => {
        if (!response.ok) {
            localStorage.removeItem('accessToken');
            window.location.href = '/login';
            throw new Error('Sessão inválida ou expirada.');
        }
        return response.json();
    })
    .then(user => {
        currentUserRole = user.role;
        document.getElementById('welcome-message').textContent = `Bem-vindo, ${user.username}!`;
        if (user.role === 'admin' || user.role === 'superuser') {
            document.getElementById('admin-link').style.display = 'inline-block';
        }
        loadUserHistory(); 
    })
    .catch((error) => {
        console.error(error.message);
        if (window.location.pathname !== '/login') {
            window.location.href = '/login';
        }
    });

    const pdfInput = document.getElementById('pdfInput');
    const fileUploadLabel = document.querySelector('.custom-file-upload');
    const defaultLabelText = fileUploadLabel.innerHTML;

    pdfInput.addEventListener('change', function(e){
      if(e.target.files && e.target.files.length > 0) {
        fileUploadLabel.innerHTML = `<i class="fas fa-file-pdf"></i> ${e.target.files[0].name}`;
      } else {
        fileUploadLabel.innerHTML = defaultLabelText;
      }
    });

    document.getElementById('logout-button').addEventListener('click', () => {
        localStorage.removeItem('accessToken');
        window.location.href = '/login';
    });

    setupSettingsModal();

    document.getElementById('cancel-button').addEventListener('click', async () => {
        if (!trackingCode) return;
        
        const btn = document.getElementById('cancel-button');
        btn.disabled = true;
        btn.textContent = 'Cancelando...';

        const token = localStorage.getItem('accessToken');
        try {
            await fetch(`/cancel-processing/${trackingCode}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
        } catch (error) {
            console.error('Erro ao cancelar:', error);
            showModal("Não foi possível cancelar o processo.");
            btn.disabled = false;
            btn.textContent = 'Cancelar';
        }
    });

    document.getElementById('history-table').addEventListener('click', function(e) {
        if (e.target.classList.contains('download-link')) {
            e.preventDefault();
            const code = e.target.dataset.code;
            const downloadUrl = (currentUserRole === 'admin' || currentUserRole === 'superuser') ? `/download/zip/${code}` : `/download/pdf/${code}`;
            const filename = (currentUserRole === 'admin' || currentUserRole === 'superuser') ? `processado_${code}.zip` : `resumo_${code}.pdf`;
            handleAuthenticatedDownload(downloadUrl, filename);
        }
    });
});

function loadUserHistory() {
    const token = localStorage.getItem('accessToken');
    fetch('/users/me/uploads', {
        headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(response => response.ok ? response.json() : Promise.reject('Failed to load history'))
    .then(uploads => {
        const tbody = document.querySelector('#history-table tbody');
        tbody.innerHTML = '';
        if (uploads.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">Nenhum histórico encontrado.</td></tr>';
            return;
        }

        uploads.forEach(upload => {
            const row = tbody.insertRow();
            const downloadBtn = upload.status === 'finished'
                ? `<a href="#" class="download-link" data-code="${upload.tracking_code}">Baixar</a>`
                : 'N/A';

            row.innerHTML = `
                <td>${upload.original_filename}</td>
                <td>${new Date(upload.upload_time).toLocaleString('pt-BR')}</td>
                <td>${upload.status}</td>
                <td>${downloadBtn}</td>
            `;
        });
    })
    .catch(error => {
        console.error('Erro ao carregar histórico:', error);
        const tbody = document.querySelector('#history-table tbody');
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">Erro ao carregar o histórico.</td></tr>';
    });
}

function setupSettingsModal() {
    const modal = document.getElementById('settings-modal');
    const btn = document.getElementById('settings-btn');
    const span = document.getElementsByClassName('close-btn')[0];

    if(!modal || !btn || !span) {
        console.error("Elementos do modal de configurações não encontrados.");
        return;
    }

    btn.onclick = function() {
        modal.style.display = 'block';
    }
    span.onclick = function() {
        modal.style.display = 'none';
    }
    window.onclick = function(event) {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    }

    document.getElementById('password-change-form').addEventListener('submit', async function(e) {
        e.preventDefault();
        const currentPassword = document.getElementById('current-password').value;
        const newPassword = document.getElementById('new-password').value;
        const statusEl = document.getElementById('password-change-status');
        const token = localStorage.getItem('accessToken');

        statusEl.textContent = 'A guardar...';
        statusEl.style.color = 'gray';

        try {
            const response = await fetch('/users/me/password', {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    current_password: currentPassword,
                    new_password: newPassword
                })
            });

            if (response.status === 204) {
                statusEl.textContent = 'Palavra-passe alterada com sucesso!';
                statusEl.style.color = 'green';
                e.target.reset();
            } else {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Falha ao alterar a palavra-passe.');
            }
        } catch (error) {
            statusEl.textContent = `Erro: ${error.message}`;
            statusEl.style.color = 'red';
        }
    });

    const darkModeToggle = document.getElementById('dark-mode-toggle');
    darkModeToggle.addEventListener('change', function() {
        document.body.classList.toggle('dark-mode');
        localStorage.setItem('darkMode', this.checked);
    });
}

function initializeDarkMode() {
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    const isDarkMode = localStorage.getItem('darkMode') === 'true';
    if(darkModeToggle) {
        darkModeToggle.checked = isDarkMode;
    }
    if (isDarkMode) {
        document.body.classList.add('dark-mode');
    }
}

async function handleAuthenticatedDownload(url, filename) {
    const token = localStorage.getItem('accessToken');
    try {
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);
        a.remove();
    } catch (error) {
        console.error('Erro no download:', error);
        showModal(`Falha no download: ${error.message}`);
    }
}

async function uploadPDF() {
  clearInterval(statusInterval);
  const token = localStorage.getItem('accessToken');
  if (!token) {
      showModal("Sessão expirada. Faça login novamente.");
      window.location.href = '/login';
      return;
  }

  const pdfInput = document.getElementById("pdfInput");
  if (!pdfInput.files.length) {
    showModal("Selecione um arquivo PDF");
    return;
  }

  const formData = new FormData();
  formData.append("file", pdfInput.files[0]);

  document.getElementById("progressSection").classList.remove("hidden");
  document.getElementById("cancel-button").classList.remove("hidden");
  document.getElementById("downloadContainer").classList.add("hidden");
  document.getElementById("statusText").textContent = "Enviando...";
  document.getElementById("progressBar").value = 5;

  try {
    const response = await fetch("/process-pdf", {
      method: "POST",
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    trackingCode = data.tracking_code;
    loadUserHistory(); 
    checkStatusLoop(trackingCode);
  } catch (error) {
    console.error('Erro ao enviar o PDF:', error);
    document.getElementById("statusText").textContent = "Erro ao enviar o arquivo.";
    document.getElementById("cancel-button").classList.add("hidden");
    showModal(`Erro ao enviar o arquivo: ${error.message}`);
    clearInterval(statusInterval);
  }
}

function checkStatusLoop(code) {
  const token = localStorage.getItem('accessToken');
  statusInterval = setInterval(async () => {
    try {
      const res = await fetch(`/processing-status/${code}`, {
          headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || `HTTP error! status: ${res.status}`);
      }
      const data = await res.json();

      const status = data.status;
      const statusInfo = statusMap[status] || { value: 0, text: "Status desconhecido" };
      document.getElementById("statusText").textContent = statusInfo.text;
      document.getElementById("progressBar").value = statusInfo.value;

      if (status === "finished" || status === "error" || status === "cancelled") {
        clearInterval(statusInterval);
        document.getElementById("cancel-button").classList.add("hidden");
        document.getElementById('cancel-button').disabled = false;
        document.getElementById('cancel-button').textContent = 'Cancelar';

        if (status === "finished") {
            const downloadLink = document.getElementById("downloadLink");
            
            let downloadUrl, downloadFilename, linkText;

            if (currentUserRole === 'admin' || currentUserRole === 'superuser') {
                downloadUrl = `/download/zip/${code}`;
                downloadFilename = `processado_${code}.zip`;
                linkText = '📦 Baixe o ZIP';
            } else {
                downloadUrl = `/download/pdf/${code}`;
                downloadFilename = `resumo_${code}.pdf`;
                linkText = '📄 Baixe o PDF';
            }

            downloadLink.textContent = linkText;
            downloadLink.removeAttribute('href');
            
            const newDownloadLink = downloadLink.cloneNode(true);
            downloadLink.parentNode.replaceChild(newDownloadLink, downloadLink);

            newDownloadLink.addEventListener('click', (e) => {
                e.preventDefault();
                handleAuthenticatedDownload(downloadUrl, downloadFilename);
            });

            document.getElementById("downloadContainer").classList.remove("hidden");
        }
        
        if (status === "error") {
            showModal("Ocorreu um erro durante o processamento do arquivo.");
        }
        loadUserHistory(); 
      }
    } catch(error) {
      console.error('Erro ao consultar status:', error);
      document.getElementById("statusText").textContent = "Erro ao consultar status.";
      showModal(`Erro ao consultar status: ${error.message}`);
      clearInterval(statusInterval);
    }
  }, 2000);
}

function showModal(message) {
    const existingModal = document.getElementById('customModal');
    if (existingModal) {
        existingModal.remove();
    }
    const modal = document.createElement('div');
    modal.id = 'customModal';
    modal.style.position = 'fixed';
    modal.style.left = '50%';
    modal.style.top = '50%';
    modal.style.transform = 'translate(-50%, -50%)';
    modal.style.padding = '25px';
    modal.style.backgroundColor = 'var(--modal-bg)';
    modal.style.color = 'var(--text-color)';
    modal.style.borderRadius = '10px';
    modal.style.boxShadow = '0 10px 25px var(--modal-shadow)';
    modal.style.zIndex = '1001';
    modal.style.textAlign = 'center';
    modal.style.minWidth = '300px';
    modal.style.maxWidth = '90%';

    const messageP = document.createElement('p');
    messageP.textContent = message;
    messageP.style.marginBottom = '20px';
    messageP.style.fontSize = '1.1em';

    const closeButton = document.createElement('button');
    closeButton.textContent = 'OK';
    closeButton.style.padding = '10px 25px';
    closeButton.style.backgroundImage = 'linear-gradient(to right, #667eea 0%, #764ba2 51%, #667eea 100%)';
    closeButton.style.backgroundSize = '200% auto';
    closeButton.style.color = 'white';
    closeButton.style.border = 'none';
    closeButton.style.borderRadius = '8px';
    closeButton.style.cursor = 'pointer';
    closeButton.style.fontSize = '1em';
    closeButton.onclick = () => modal.remove();

    modal.appendChild(messageP);
    modal.appendChild(closeButton);
    document.body.appendChild(modal);
}