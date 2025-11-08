# Airflow UI Login Guide ✅

## Quick Answer

### ✅ Username: `airflow`
### ✅ Password: `airflow`

---

## Access Information

| Component | URL | Default Port |
|-----------|-----|--------------|
| **Airflow UI** | http://localhost:8080 | 8080 |
| **API** | http://localhost:8000 | 8000 |
| **Dashboard** | http://localhost:8501 | 8501 |

---

## How to Login

### Step 1: Open Browser
Go to **http://localhost:8080**

### Step 2: Enter Credentials
```
Username: airflow
Password: airflow
```

### Step 3: Click Login
You should now see the Airflow Dashboard! ✅

---

## What's Inside Airflow UI

Once logged in, you'll see:

### 📊 DAGs Page
- Shows all 3 DAGs:
  - `eval_runner_dag` ← Your evaluation DAG
  - `ai50_daily_refresh_dag`
  - `ai50_full_ingest_dag`

### 🎯 Tasks
- 8 tasks in eval_runner_dag:
  - `load_companies` - Loads company data
  - `evaluate_*_structured` - Evaluation tasks
  - `evaluate_*_rag` - RAG pipeline tasks
  - `generate_comparison_report` - Final report

### 📈 Monitoring
- View DAG runs
- Check task status
- View logs
- Monitor execution

---

## If You Still Can't Login

### Problem: "Login failed" message

**Solution 1**: Wait 30 seconds and refresh
- Database might still be initializing

**Solution 2**: Check user creation
```bash
docker-compose exec airflow-scheduler airflow users list
```

**Solution 3**: Create user manually
```bash
docker-compose exec airflow-scheduler airflow users create \
  --username airflow \
  --password airflow \
  --firstname Airflow \
  --lastname Admin \
  --role Admin \
  --email admin@example.com
```

### Problem: Page shows "500 Error"

**Solution**: Restart webserver
```bash
docker-compose restart airflow-webserver
```

### Problem: Can't access http://localhost:8080

**Solution 1**: Check if container is running
```bash
docker-compose ps airflow-webserver
```

**Solution 2**: Check if port 8080 is in use
```powershell
netstat -ano | findstr :8080
```

**Solution 3**: View webserver logs
```bash
docker-compose logs airflow-webserver
```

---

## User Roles & Permissions

### Available Roles
- **Admin** ← Current user (airflow)
  - Full access to all features
  - Can create, modify, delete DAGs
  - Can trigger DAG runs
  - Can view logs and metrics

- **User** - Can view and trigger DAGs
- **Op** - Can only view DAGs
- **Viewer** - Read-only access

---

## First Steps After Login

### 1. ✅ Verify DAGs Are Loaded
- Go to "DAGs" tab
- Should see 3 DAGs listed
- Click on `eval_runner_dag`

### 2. ✅ Check Tasks
- Inside the DAG view
- Should see 8 tasks in tree view
- Shows dependencies and status

### 3. ✅ Trigger a Test Run
- Click "Trigger DAG" button (or play icon)
- Watch tasks execute in real-time
- Check logs for any errors

### 4. ✅ Monitor Execution
- "Graph View" shows dependencies
- "Tree View" shows execution history
- "Admin" → "Logs" shows detailed task logs

---

## Useful Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `?` | Show keyboard shortcuts |
| `g` then `h` | Go to Home |
| `g` then `d` | Go to DAGs |
| `g` then `a` | Go to Admin |
| `g` then `l` | Go to Logs |

---

## Common Tasks

### Trigger a DAG Run
1. Go to DAGs
2. Find the DAG
3. Click the "Play" icon or "Trigger DAG" button
4. Optionally set parameters
5. Click "Trigger" to confirm

### View Task Logs
1. Click on a DAG run
2. Click on a task instance
3. Click "Log" tab to see output

### Check DAG Health
1. Click on a DAG
2. Look at the "DAG Details" panel
3. Check recent run statistics

---

## Settings & Configuration

### Access Settings
Navigate to: **Admin** → **Configuration**

Here you can see:
- Executor type (LocalExecutor)
- Database connection string
- All environment variables
- Airflow version (2.10.4)

### View Connections
Navigate to: **Admin** → **Connections**

Predefined connections:
- PostgreSQL database
- API endpoints
- Custom integrations

### Manage Users
Navigate to: **Admin** → **Users**

You can:
- Create new users
- Edit user roles
- Reset passwords
- View all users

---

## API Access

### REST API (Port 8000)
```bash
# Example: Get DAG info via API
curl http://localhost:8000/api/v1/dags/eval_runner_dag
```

### Authentication
- Username: `airflow`
- Password: `airflow`
- Bearer token available in UI

---

## Troubleshooting

### DAGs Not Showing
```bash
# Check DAG parsing
docker-compose exec airflow-scheduler airflow dags list
```

### Tasks Not Running
```bash
# Check scheduler logs
docker-compose logs airflow-scheduler | tail -50
```

### Authentication Issues
```bash
# Check webserver logs
docker-compose logs airflow-webserver | grep -i "login\|auth"
```

### Database Connection Failed
```bash
# Test database
docker-compose exec postgres psql -U airflow -d airflow -c "SELECT 1"
```

---

## Reset Everything

### Restart Airflow
```bash
docker-compose restart
```

### Reset Database (WARNING: Deletes all data)
```bash
docker-compose down -v
docker-compose up -d
```

### Reset User Password
```bash
docker-compose exec airflow-scheduler airflow users reset-password \
  --username airflow \
  --password newpassword
```

---

## Credentials Summary

```
┌─────────────────────────────────┐
│   AIRFLOW LOGIN CREDENTIALS      │
├─────────────────────────────────┤
│ Username: airflow               │
│ Password: airflow               │
│ Role: Admin                      │
│ Email: admin@example.com        │
│ First Name: Airflow             │
│ Last Name: Admin                │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│   DATABASE CREDENTIALS           │
├─────────────────────────────────┤
│ User: airflow                   │
│ Password: airflow               │
│ Database: airflow               │
│ Host: postgres                  │
│ Port: 5432                      │
└─────────────────────────────────┘
```

---

## Support

For more information:
- Airflow Documentation: https://airflow.apache.org/docs/
- UI Help: Press `?` in the Airflow UI
- Logs: Check `docker-compose logs [service]`

---

**Status**: ✅ Ready to Use  
**Last Updated**: November 8, 2025  
**Airflow Version**: 2.10.4  
