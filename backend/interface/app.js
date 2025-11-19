const { createApp } = Vue;

// const API_BASE = 'http://127.0.0.1:8000';
const API_BASE = 'https://prospection-system.multimodal-house.fr';

createApp({
  data() {
    return {
      token: localStorage.getItem('token') || '',
      workflowRunning: false,
      quotas: {},
      activity: {},
      validations: [],
      recentLogs: [],
      pollInterval: null,
      loading: false,
      statusMessage: null
    }
  },

  async mounted() {
    if (!this.token) {
      window.location.href = '/login-page';
      return;
    }

    await this.fetchDashboard();

    this.pollInterval = setInterval(() => {
      this.fetchDashboard();
    }, 10000);
  },

  beforeUnmount() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
    }
  },

  methods: {
    async fetchDashboard() {
      if (!this.token) return;

      try {
        const [workflowRes, validationsRes, quotaRes, activityRes, logsRes] = await Promise.all([
          fetch(`${API_BASE}/workflow/status`, {
            headers: { 'Authorization': `Bearer ${this.token}` }
          }),
          fetch(`${API_BASE}/validations/pending?limit=10`, {
            headers: { 'Authorization': `Bearer ${this.token}` }
          }),
          fetch(`${API_BASE}/stats/quota`, {
            headers: { 'Authorization': `Bearer ${this.token}` }
          }),
          fetch(`${API_BASE}/stats/activity`, {
            headers: { 'Authorization': `Bearer ${this.token}` }
          }),
          fetch(`${API_BASE}/logs?limit=20`, {
            headers: { 'Authorization': `Bearer ${this.token}` }
          })
        ]);

        if (workflowRes.ok) {
          const workflowData = await workflowRes.json();
          this.workflowRunning = workflowData.running;
        }

        if (validationsRes.ok) {
          const validationsData = await validationsRes.json();
          this.validations = validationsData.validations || [];
        }

        if (quotaRes.ok) {
          const quotaData = await quotaRes.json();
          this.quotas = quotaData.quotas || {};
        }

        if (activityRes.ok) {
          const activityData = await activityRes.json();
          this.activity = activityData.activity || {};
        }

        if (logsRes.ok) {
          const logsData = await logsRes.json();
          this.recentLogs = logsData.logs || [];
        }

      } catch (error) {
        console.error('Error fetching dashboard:', error);
      }
    },

    async toggleWorkflow() {
      if (this.loading) return;

      this.loading = true;
      const endpoint = this.workflowRunning ? '/workflow/stop' : '/workflow/start';

      try {
        const res = await fetch(`${API_BASE}${endpoint}`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${this.token}`
          }
        });

        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.detail || 'Operation failed');
        }

        this.showMessage(data.message, 'success');
        await this.fetchDashboard();
      } catch (error) {
        console.error('Toggle error:', error);
        this.showMessage('Erreur: ' + error.message, 'error');
        await this.fetchDashboard();
      } finally {
        this.loading = false;
      }
    },

    async approveValidation(logId) {
      if (this.loading) return;

      this.loading = true;

      try {
        const res = await fetch(`${API_BASE}/validations/${logId}/approve`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${this.token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({})
        });

        if (!res.ok) {
          const error = await res.json();
          throw new Error(error.detail || 'Approval failed');
        }

        this.showMessage('Validation approuvée', 'success');
        await this.fetchDashboard();
      } catch (error) {
        this.showMessage('Erreur: ' + error.message, 'error');
      } finally {
        this.loading = false;
      }
    },

    async rejectValidation(logId) {
      if (this.loading) return;

      this.loading = true;

      try {
        const res = await fetch(`${API_BASE}/validations/${logId}/reject`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${this.token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            reason: 'Rejected from dashboard'
          })
        });

        if (!res.ok) {
          const error = await res.json();
          throw new Error(error.detail || 'Rejection failed');
        }

        this.showMessage('Validation rejetée', 'success');
        await this.fetchDashboard();
      } catch (error) {
        this.showMessage('Erreur: ' + error.message, 'error');
      } finally {
        this.loading = false;
      }
    },

    showMessage(text, type = 'success') {
      this.statusMessage = { text, type };
      setTimeout(() => {
        this.statusMessage = null;
      }, 3000);
    },

    formatActionType(key) {
      const labels = {
        'send_first_contact': 'Premier contact',
        'send_followup_a_1': 'Relance A1',
        'send_followup_a_2': 'Relance A2',
        'send_followup_a_3': 'Relance A3',
        'send_followup_b': 'Relance B',
        'send_followup_c': 'Relance C',
        'connections': 'Connexions'
      };
      return labels[key] || key;
    },

    formatDate(dateStr) {
      if (!dateStr) return 'N/A';
      return new Date(dateStr).toLocaleString('fr-FR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
    },

    logout() {
      localStorage.removeItem('token');
      window.location.href = '/login-page';
    }
  }
}).mount('#app');
