let trackingCode = "";
let statusInterval;
let currentUserRole = "user";

const statusMap = {
  received: { value: 10, text: "Arquivo recebido" },
  preparing: { value: 20, text: "Lendo arquivo" },
  uploading: { value: 30, text: "Enviando arquivo para processamento..." },
  question_answering: { value: 40, text: "Respondendo perguntas..." },
  summarizing: { value: 60, text: "Gerando resumo..." },
  generating_pdf: { value: 80, text: "Gerando Documentos..." },
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
        const welcomeMessage = document.getElementById('welcome-message');
        if (welcomeMessage) {
            welcomeMessage.textContent = `Bem-vindo, ${user.username}!`;
        }
        const adminLink = document.getElementById('admin-link');
        if (adminLink && (user.role === 'admin' || user.role === 'superuser')) {
            adminLink.style.display = 'inline-block';
        }
        loadUserHistory(); 
    })
    .catch((error) => {
        if (window.location.pathname !== '/login') {
            window.location.href = '/login';
        }
    });

    const pdfInput = document.getElementById('pdfInput');
    const fileUploadText = document.getElementById('upload-label-text');
    if (pdfInput && fileUploadText) {
        const defaultLabelText = fileUploadText.textContent;
        pdfInput.addEventListener('change', function(e){
          if(e.target.files && e.target.files.length > 0) {
            fileUploadText.innerHTML = `<i class="fas fa-file-pdf"></i> ${e.target.files[0].name}`;
          } else {
            fileUploadText.textContent = defaultLabelText;
          }
        });
    }

    const logoutButton = document.getElementById('logout-button');
    if (logoutButton) {
        logoutButton.addEventListener('click', () => {
            localStorage.removeItem('accessToken');
            window.location.href = '/login';
        });
    }

    setupSettingsModal();

    const cancelButton = document.getElementById('cancel-button');
    if (cancelButton) {
        cancelButton.addEventListener('click', async () => {
            if (!trackingCode) return;
            
            cancelButton.disabled = true;
            cancelButton.textContent = 'Cancelando...';
            document.getElementById("robot-state").src = "../frontend/img/BOT_IDLE.png";

            const token = localStorage.getItem('accessToken');
            try {
                await fetch(`/cancel-processing/${trackingCode}`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
            } catch (error) {
                showModal("Não foi possível cancelar o processo.");
                cancelButton.disabled = false;
                cancelButton.textContent = 'Cancelar';
            }
        });
    }

    const historyTable = document.getElementById('history-table');
    if (historyTable) {
        historyTable.addEventListener('click', function(e) {
            if (e.target.classList.contains('download-link')) {
                e.preventDefault();
                const code = e.target.dataset.code;
                const type = e.target.dataset.type;
                
                let downloadUrl, filename;
                
                if (type === 'zip') {
                    downloadUrl = `/download/zip/${code}`;
                    filename = `processado_${code}.zip`;
                } else if (type === 'word') {
                    downloadUrl = `/download/word/${code}`;
                    filename = `esboco_${code}.docx`;
                } else {
                    downloadUrl = `/download/pdf/${code}`;
                    filename = `analise_${code}.pdf`;
                }
                
                handleAuthenticatedDownload(downloadUrl, filename);
            }
        });
    }
});

function loadUserHistory() {
    const tbody = document.querySelector('#history-table tbody');
    if (!tbody) return;

    const token = localStorage.getItem('accessToken');
    fetch('/users/me/uploads', {
        headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(response => response.ok ? response.json() : Promise.reject('Failed to load history'))
    .then(uploads => {
        tbody.innerHTML = '';
        if (uploads.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">Nenhum histórico encontrado.</td></tr>';
            return;
        }

        uploads.forEach(upload => {
            const row = tbody.insertRow();
            
            let downloadBtn = 'N/A';
            if (upload.status === 'finished') {
                if (currentUserRole === 'admin' || currentUserRole === 'superuser') {
                    downloadBtn = `<a href="#" class="download-link" data-code="${upload.tracking_code}" data-type="zip">ZIP</a>`;
                } else {
                    downloadBtn = `
                        <a href="#" class="download-link" data-code="${upload.tracking_code}" data-type="pdf">PDF</a> | 
                        <a href="#" class="download-link" data-code="${upload.tracking_code}" data-type="word">Word</a>
                    `;
                }
            }

            row.innerHTML = `
                <td>${upload.original_filename}</td>
                <td>${new Date(upload.upload_time).toLocaleString('pt-BR')}</td>
                <td>${upload.status}</td>
                <td>${downloadBtn}</td>
            `;
        });
    })
    .catch(error => {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">Erro ao carregar o histórico.</td></tr>';
    });
}

function setupSettingsModal() {
    const modal = document.getElementById('settings-modal');
    const btn = document.getElementById('settings-btn');
    const spans = document.getElementsByClassName('close-btn');

    if(!modal || !btn || spans.length === 0) {
        return;
    }

    const span = spans[0];

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

    const passwordForm = document.getElementById('password-change-form');
    if (passwordForm) {
        passwordForm.addEventListener('submit', async function(e) {
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
    }

    const darkModeToggle = document.getElementById('dark-mode-toggle');
    if (darkModeToggle) {
        darkModeToggle.addEventListener('change', function() {
            document.body.classList.toggle('dark-mode');
            localStorage.setItem('darkMode', this.checked);
        });
    }
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
  if (!pdfInput || !pdfInput.files.length) {
    showModal("Selecione um arquivo PDF");
    return;
  }

  document.getElementById("robot-state").src = "../frontend/img/BOT_LOADING.png";

  const formData = new FormData();
  formData.append("file", pdfInput.files[0]);

  const cancelBtn = document.getElementById("cancel-button");
  const downloadContainer = document.getElementById("downloadContainer");
  const statusText = document.getElementById("statusText");
  const progressBar = document.getElementById("progressBar");

  if(cancelBtn) cancelBtn.classList.remove("hidden");
  if(downloadContainer) downloadContainer.classList.add("hidden");
  if(statusText) statusText.textContent = "Enviando...";
  if(progressBar) progressBar.value = 5;

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
    document.getElementById("robot-state").src = "../frontend/img/BOT_SAD.png";
    if(statusText) statusText.textContent = "Erro ao enviar o arquivo.";
    if(cancelBtn) cancelBtn.classList.add("hidden");
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
      
      const statusText = document.getElementById("statusText");
      const progressBar = document.getElementById("progressBar");
      
      if(statusText) statusText.textContent = statusInfo.text;
      if(progressBar) progressBar.value = statusInfo.value;

      if (status === "finished" || status === "error" || status === "cancelled") {
        clearInterval(statusInterval);
        
        const cancelButton = document.getElementById("cancel-button");
        if(cancelButton) {
            cancelButton.classList.add("hidden");
            cancelButton.disabled = false;
            cancelButton.textContent = 'Cancelar';
        }

        if (status === "finished") {
            document.getElementById("robot-state").src = "../frontend/img/BOT_IDLE.png";
            const pdfLink = document.getElementById("downloadPdfLink");
            const wordLink = document.getElementById("downloadWordLink");
            const zipLink = document.getElementById("downloadZipLink");
            const downloadContainer = document.getElementById("downloadContainer");
            
            if(pdfLink) pdfLink.onclick = (e) => { e.preventDefault(); handleAuthenticatedDownload(`/download/pdf/${code}`, `analise_${code}.pdf`); };
            if(wordLink) wordLink.onclick = (e) => { e.preventDefault(); handleAuthenticatedDownload(`/download/word/${code}`, `esboco_${code}.docx`); };

            if(downloadContainer) downloadContainer.classList.remove("hidden");

            if (zipLink) {
                if (currentUserRole === 'admin' || currentUserRole === 'superuser') {
                    zipLink.classList.remove("hidden");
                    zipLink.onclick = (e) => { e.preventDefault(); handleAuthenticatedDownload(`/download/zip/${code}`, `processado_${code}.zip`); };
                } else {
                    zipLink.classList.add("hidden");
                }
            }
        }
        
        if (status === "error") {
            document.getElementById("robot-state").src = "../frontend/img/BOT_SAD.png";
            showModal("Ocorreu um erro durante o processamento do arquivo.");
        }

        if (status === "cancelled") {
            document.getElementById("robot-state").src = "../frontend/img/BOT_IDLE.png";
        }
        
        loadUserHistory(); 
      }
    } catch(error) {
      document.getElementById("robot-state").src = "../frontend/img/BOT_SAD.png";
      const statusText = document.getElementById("statusText");
      if(statusText) statusText.textContent = "Erro ao consultar status.";
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
    closeButton.style.backgroundImage = 'linear-gradient(to right, #6366f1 0%, #4f46e5 51%, #6366f1 100%)';
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