document.addEventListener('DOMContentLoaded', function() {
    const token = localStorage.getItem('accessToken');
    if (!token) {
        window.location.href = '/login';
        return;
    }

    initializeAdminDarkMode();

    const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    };

    async function verifyAdminAccess() {
        try {
            const response = await fetch('/users/me', { headers });
            if (!response.ok) throw new Error('Falha na autenticação');
            
            const user = await response.json();
            if (user.role !== 'admin' && user.role !== 'superuser') {
                alert('Acesso negado.');
                window.location.href = '/app';
                return;
            }
            loadDashboard();
        } catch (error) {
            console.error(error.message);
            localStorage.removeItem('accessToken');
            window.location.href = '/login';
        }
    }

    function loadDashboard() {
        fetchAdminData();
        fetchUsers();
    }

    function fetchAdminData() {
        fetch('/admin/dashboard', { headers })
            .then(response => response.json())
            .then(data => {
                populateStatsTable(data.user_stats);
                populateUploadsTable(data.recent_uploads);
            })
            .catch(err => console.error("Erro ao carregar dashboard:", err));
    }

    function fetchUsers() {
        fetch('/admin/users', { headers })
            .then(response => response.json())
            .then(populateUsersTable)
            .catch(err => console.error("Erro ao carregar usuários:", err));
    }

    function populateStatsTable(stats) {
        const tbody = document.querySelector('#stats-table tbody');
        tbody.innerHTML = '';
        if (!stats || stats.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">Nenhuma estatística encontrada.</td></tr>';
            return;
        }
        stats.forEach(stat => {
            const row = tbody.insertRow();
            row.innerHTML = `
                <td>${stat.user ? stat.user.username : 'Desconhecido'}</td>
                <td>${stat.files_uploaded_count || 0}</td>
                <td>${stat.request_count || 0}</td>
                <td>${stat.last_activity ? new Date(stat.last_activity).toLocaleString('pt-BR') : 'N/A'}</td>
            `;
        });
    }

    function populateUploadsTable(uploads) {
        const tbody = document.querySelector('#uploads-table tbody');
        tbody.innerHTML = '';
        if (!uploads || uploads.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">Nenhum upload recente.</td></tr>';
            return;
        }
        uploads.forEach(upload => {
            const row = tbody.insertRow();
            const downloadLink = upload.status === 'finished' 
                ? `<a href="#" class="download-zip-link" data-code="${upload.tracking_code}">Baixar ZIP</a>`
                : upload.status;
            row.innerHTML = `
                <td>${upload.owner ? upload.owner.username : 'Desconhecido'}</td>
                <td>${upload.original_filename || 'N/A'}</td>
                <td>${upload.upload_time ? new Date(upload.upload_time).toLocaleString('pt-BR') : 'N/A'}</td>
                <td>${upload.status || 'N/A'}</td>
                <td>${downloadLink}</td>
            `;
        });
    }
    
    function populateUsersTable(users) {
        const tbody = document.querySelector('#users-table tbody');
        tbody.innerHTML = '';
        if(!users) return;
        users.forEach(user => {
            const row = tbody.insertRow();
            // Garanta que o atributo seja data-username (minúsculo)
            const deleteBtn = `<button class="delete-btn" data-username="${user.username}">Deletar</button>`;
            
            row.innerHTML = `
                <td>${user.username}</td>
                <td>${user.role}</td>
                <td>${user.created_at || '-'}</td>
                <td>${user.role !== 'superuser' ? deleteBtn : ''}</td>
            `;
        });
    }

    document.querySelector('#uploads-table').addEventListener('click', e => {
        if (e.target.classList.contains('download-zip-link')) {
            e.preventDefault();
            const code = e.target.dataset.code;
            handleAuthenticatedDownload(`/download/zip/${code}`, `processado_${code}.zip`);
        }
    });

    document.querySelector('#users-table').addEventListener('click', e => {
        if (e.target.classList.contains('delete-btn')) {
            const username = e.target.getAttribute('data-username'); // Captura explícita
            if (username && username !== "undefined") {
                if (confirm(`Tem certeza que deseja deletar o utilizador ${username}?`)) {
                    deleteUser(username);
                }
            } else {
                alert("Erro: Username não encontrado no botão.");
            }
        }
    });

    document.getElementById('create-user-btn').addEventListener('click', () => {
        const username = document.getElementById('new-username').value;
        const password = document.getElementById('new-password').value;
        const role = document.getElementById('new-user-role').value;

        if (!username || !password) {
            alert('Nome de utilizador e palavra-passe são obrigatórios.');
            return;
        }

        fetch('/admin/users', {
            method: 'POST',
            headers,
            body: JSON.stringify({ username, password, role })
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => { throw new Error(err.detail || 'Falha ao criar utilizador.') });
            }
            return response.json();
        })
        .then(() => {
            alert('Utilizador criado com sucesso!');
            fetchUsers();
            document.getElementById('new-username').value = '';
            document.getElementById('new-password').value = '';
        })
        .catch(err => alert(err.message));
    });

    function deleteUser(username) {
        fetch(`/admin/users/${username}`, { method: 'DELETE', headers })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw new Error(err.detail || 'Não foi possível apagar o utilizador.') });
                }
                alert('Utilizador apagado com sucesso.');
                fetchUsers();
            })
            .catch(err => alert(err.message));
    }

    async function handleAuthenticatedDownload(url, filename) {
        try {
            const response = await fetch(url, { headers });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

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
            alert(`Falha no download. O arquivo pode não estar pronto.`);
        }
    }
    
    document.getElementById('logout-button').addEventListener('click', () => {
        localStorage.removeItem('accessToken');
        window.location.href = '/login';
    });

    function initializeAdminDarkMode() {
        const darkModeToggle = document.getElementById('dark-mode-toggle');
        const isDarkMode = localStorage.getItem('darkMode') === 'true';
        if(darkModeToggle) {
            darkModeToggle.checked = isDarkMode;
            if (isDarkMode) document.body.classList.add('dark-mode');
            darkModeToggle.addEventListener('change', function() {
                document.body.classList.toggle('dark-mode');
                localStorage.setItem('darkMode', this.checked);
            });
        }
    }

    verifyAdminAccess();
});