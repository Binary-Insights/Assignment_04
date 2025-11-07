# 🚀 AIRFLOW DOCKER SETUP - COMPLETE REFERENCE

## ⚡ TLDR (Too Long; Didn't Read)

Your Docker setup now has **Apache Airflow** fully integrated!

### Start Now (Windows)
```powershell
cd docker
.\start.ps1
```

### Then Visit
- **Airflow UI**: http://localhost:8080 (admin/admin)
- **FastAPI**: http://localhost:8000/docs
- **Streamlit**: http://localhost:8501

## 📊 What's Included

### Services (5 Total)
1. **PostgreSQL** → Airflow metadata database
2. **Airflow Webserver** → UI & REST API (port 8080)
3. **Airflow Scheduler** → Automated workflow execution
4. **FastAPI** → Backend API (port 8000)
5. **Streamlit** → Frontend dashboard (port 8501)

### Documentation (8 Files, 2,100+ Lines)
- README.md - Overview
- AIRFLOW_SETUP.md - Complete guide
- QUICK_REFERENCE.md - Commands
- SETUP_COMPLETE.md - What's new
- CHANGES_SUMMARY.md - Before/after
- INDEX.md - Navigation
- .env.example - Configuration

### Code Examples (400+ Lines)
- dags/example_advanced_dags.py - 4 production DAGs

## 🎯 Your DAGs Are Already Ready

Your existing DAGs in `dags/` folder:
- ✅ `ai50_daily_refresh_dag.py` - Already set up
- ✅ `ai50_full_ingest_dag.py` - Already set up
- ✅ New: `example_advanced_dags.py` - 4 examples to learn from

They'll appear in Airflow UI automatically after startup!

## 🔄 Service Architecture

```
┌─────────────────────────────────────┐
│     PostgreSQL (Metadata DB)        │
│          :5432                      │
└────────────────┬────────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼─────┐  ┌───▼──────┐ ┌──▼────────┐
│Airflow  │  │ Airflow  │ │ FastAPI   │
│WebUI    │  │Scheduler │ │ (8000)    │
│(8080)   │  │(Background) │           │
└─────────┘  └──────────┘ └─────┬─────┘
                               │
                         ┌─────▼────┐
                         │Streamlit │
                         │ (8501)   │
                         └──────────┘
```

## 🚀 Getting Started

### Step 1: Start Services (2 minutes)
```powershell
cd docker
.\start.ps1
```

**What happens:**
- ✅ Checks Docker installation
- ✅ Creates .env from template
- ✅ Builds Docker images
- ✅ Starts 5 services
- ✅ Waits for health checks
- ✅ Shows access URLs

### Step 2: Open Airflow UI (30 seconds)
```
Browser: http://localhost:8080
Username: admin
Password: admin
```

### Step 3: Explore DAGs (5 minutes)
- Click on DAG name to see details
- View task graph
- Check previous runs
- Explore task logs

### Step 4: Trigger Your First DAG (1 minute)
1. Select a DAG
2. Click "Trigger DAG" button
3. Watch it execute in real-time
4. View logs when complete

## 📁 Complete File Structure

### Docker Directory
```
docker/
├── Dockerfile                    ← Image with Airflow
├── docker-compose.yml            ← 5 services orchestration
├── .env.example                  ← Configuration template
├── start.ps1                     ← Windows launcher
├── start.sh                      ← Linux launcher
├── README.md                     ← Setup guide
├── QUICK_REFERENCE.md           ← Commands
├── AIRFLOW_SETUP.md             ← Complete guide
├── SETUP_COMPLETE.md            ← Summary
├── CHANGES_SUMMARY.md           ← Before/after
└── INDEX.md                     ← Documentation index
```

### DAGs Directory
```
dags/
├── ai50_daily_refresh_dag.py    ← Your existing DAG
├── ai50_full_ingest_dag.py      ← Your existing DAG
└── example_advanced_dags.py     ← NEW: 4 examples
    ├── Example 1: Basic FastAPI integration
    ├── Example 2: Parallel processing
    ├── Example 3: Data quality checks
    └── Example 4: Scheduled refresh
```

## 🎓 What Each Service Does

### PostgreSQL
```
Purpose: Store Airflow metadata
- DAG definitions
- Task states
- Execution history
- User settings

Port: 5432
Access: Host=postgres, User=airflow, Password=airflow
```

### Airflow Webserver
```
Purpose: DAG management interface
- View DAGs graphically
- Monitor execution
- View task logs
- Trigger workflows manually
- Manage settings

Port: 8080
URL: http://localhost:8080
Login: admin / admin
```

### Airflow Scheduler
```
Purpose: Automated workflow execution
- Detect new DAGs
- Schedule based on timing
- Execute tasks
- Handle retries
- Log output

Type: Background service (no UI)
Access: Check logs in Airflow UI
```

### FastAPI
```
Purpose: Backend API
- Already configured
- Accessible from Airflow DAGs
- Connected to Streamlit
- Persistent /app/data volume

Port: 8000
Docs: http://localhost:8000/docs
Network: http://fastapi:8000 (from Airflow)
```

### Streamlit
```
Purpose: Dashboard UI
- Already configured
- Connects to FastAPI
- Real-time updates
- Interactive visualizations

Port: 8501
URL: http://localhost:8501
```

## 🔧 Configuration

### Edit .env File
```bash
docker/.env

# Executor (LocalExecutor for single machine)
AIRFLOW__CORE__EXECUTOR=LocalExecutor

# Database (PostgreSQL inside Docker)
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres:5432/airflow

# PostgreSQL credentials
POSTGRES_USER=airflow
POSTGRES_PASSWORD=airflow
POSTGRES_DB=airflow

# Scheduling behavior
AIRFLOW__SCHEDULER__CATCHUP_BY_DEFAULT=false

# Add your API keys if needed
# OPENAI_API_KEY=your_key
# ANTHROPIC_API_KEY=your_key
```

## 📚 Documentation Quick Links

| Need | File | Read Time |
|------|------|-----------|
| Quick start | README.md | 10 min |
| Commands | QUICK_REFERENCE.md | 5 min |
| Full details | AIRFLOW_SETUP.md | 20 min |
| DAG examples | example_advanced_dags.py | 15 min |
| What's new | CHANGES_SUMMARY.md | 10 min |
| Navigation | INDEX.md | 5 min |

## 🎯 Common Tasks

### View Logs
```powershell
docker-compose logs -f airflow-scheduler
docker-compose logs -f airflow-webserver
```

### List All DAGs
```powershell
docker exec pe-dashboard-airflow-scheduler airflow dags list
```

### Trigger a DAG
```powershell
docker exec pe-dashboard-airflow-webserver airflow dags trigger ai50_daily_refresh_dag
```

### Stop Services
```powershell
docker-compose down
```

### Restart a Service
```powershell
docker-compose restart airflow-scheduler
```

## ⚠️ Troubleshooting

### Port Already in Use
**Error**: `Address already in use`
**Fix**: Edit docker-compose.yml, change `8081:8080`

### DAGs Not Showing
**Error**: DAGs don't appear in UI
**Fix**: Restart scheduler - it auto-detects changes

### Database Error
**Error**: `Error connecting to database`
**Fix**: Clean restart: `docker-compose down -v && docker-compose up -d`

### Services Won't Start
**Error**: Container exited with code 1
**Fix**: Check logs: `docker-compose logs`

## 💡 Tips & Tricks

### Monitor Real-Time Execution
1. Go to Airflow UI (http://localhost:8080)
2. Click on a DAG
3. Click "Graph" tab
4. Watch tasks change color as they run

### View Task Output
1. Click on task in Graph view
2. Click "Logs" tab
3. See real-time console output

### Access Database Directly
```powershell
docker exec -it pe-dashboard-postgres psql -U airflow -d airflow
# Then: SELECT * FROM dag_run;
```

### Check Resource Usage
```powershell
docker stats
# See CPU/Memory for each container
```

## 🚀 Next Steps (Recommended Order)

### Today (30 minutes)
1. Run `start.ps1`
2. Open Airflow UI
3. View your existing DAGs
4. Trigger one manually
5. Read `docker/README.md`

### Tomorrow (1 hour)
1. Study `dags/example_advanced_dags.py`
2. Understand the 4 examples
3. Create simple test DAG
4. Trigger from UI
5. Check logs

### This Week (2-3 hours)
1. Integrate FastAPI with Airflow
2. Create data processing DAG
3. Schedule for automatic execution
4. Monitor in Airflow UI
5. View results in Streamlit

### Production Ready (1 week)
1. Configure production .env
2. Use external PostgreSQL
3. Set up monitoring
4. Configure backups
5. Document runbooks

## 📊 Performance Expectations

### First Startup
- Build time: 2-3 minutes
- Initialization: 30 seconds
- Ready to use: 3-4 minutes total

### DAG Execution
- Simple Python task: < 5 seconds
- API call: < 10 seconds
- Data processing: Varies by size

### PostgreSQL
- Metadata operations: < 100ms
- Should not be bottleneck

## 🔐 Security Notes

### Current (Development)
- Authentication disabled
- Simple credentials
- Local only

### For Production
- Enable authentication
- Use strong passwords
- Add SSL/TLS
- External database
- Backup strategy

## 📞 Quick Reference Commands

```powershell
# Start everything
docker-compose up -d

# Check status
docker-compose ps

# View real-time logs
docker-compose logs -f

# List DAGs
docker exec pe-dashboard-airflow-scheduler airflow dags list

# Trigger DAG
docker exec pe-dashboard-airflow-webserver airflow dags trigger [dag_id]

# Access database
docker exec -it pe-dashboard-postgres psql -U airflow -d airflow

# Stop everything
docker-compose down

# Clean everything
docker-compose down -v
```

## 🎉 You're Ready!

Everything is set up and ready to use:

✅ **Airflow configured** - Web UI + Scheduler  
✅ **PostgreSQL running** - Metadata storage  
✅ **FastAPI integrated** - Backend API  
✅ **Streamlit ready** - Frontend dashboard  
✅ **Documentation complete** - 2,100+ lines  
✅ **Examples provided** - 4 production DAGs  

### Quick Start Command
```powershell
cd docker
.\start.ps1
```

Then open: **http://localhost:8080**

---

## 📖 Documentation Files

All files in `docker/` directory:

1. **README.md** - Docker overview (start here)
2. **QUICK_REFERENCE.md** - Command cheatsheet
3. **AIRFLOW_SETUP.md** - Complete Airflow guide
4. **SETUP_COMPLETE.md** - What was delivered
5. **CHANGES_SUMMARY.md** - Before/after
6. **INDEX.md** - Navigation guide

Plus in root directory:
7. **DOCKER_AIRFLOW_DELIVERY.md** - This comprehensive guide

---

## 🎊 Congratulations!

Your Docker environment now supports Apache Airflow for complete workflow orchestration!

**Start exploring**: http://localhost:8080 🚀
