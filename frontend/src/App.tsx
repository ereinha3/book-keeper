import { useMemo, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { AppBar, Box, Container, Tab, Tabs, Toolbar } from "@mui/material";
import LibraryBooksOutlined from "@mui/icons-material/LibraryBooksOutlined";
import LocalLibraryOutlined from "@mui/icons-material/LocalLibraryOutlined";
import ViewQuiltOutlined from "@mui/icons-material/ViewQuiltOutlined";
import DashboardOutlined from "@mui/icons-material/DashboardOutlined";
import SearchView from "./views/SearchView";
import InventoryView from "./views/InventoryView";
import ShelvesView from "./views/ShelvesView";
import ShelfOverview from "./views/ShelfOverview";

interface TabConfig {
  label: string;
  icon: ReactElement;
  content: ReactNode;
}

function TabPanel({
  index,
  value,
  children,
}: {
  index: number;
  value: number;
  children: ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`app-tabpanel-${index}`}
      aria-labelledby={`app-tab-${index}`}
    >
      {value === index && <Box sx={{ pt: 4 }}>{children}</Box>}
    </div>
  );
}

const tabA11yProps = (index: number) => ({
  id: `app-tab-${index}`,
  "aria-controls": `app-tabpanel-${index}`,
});

export default function App() {
  const [currentTab, setCurrentTab] = useState(0);

  const tabs = useMemo<TabConfig[]>(
    () => [
      {
        label: "Search Library",
        icon: <LibraryBooksOutlined fontSize="small" />,
        content: <SearchView />,
      },
      {
        label: "My Collection",
        icon: <LocalLibraryOutlined fontSize="small" />,
        content: <InventoryView />,
      },
      {
        label: "Shelves & Rows",
        icon: <ViewQuiltOutlined fontSize="small" />,
        content: <ShelvesView />,
      },
      {
        label: "Shelf Overview",
        icon: <DashboardOutlined fontSize="small" />,
        content: <ShelfOverview />,
      },
    ],
    []
  );

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default", color: "text.primary" }}>
      <AppBar
        position="sticky"
        elevation={0}
        color="transparent"
        sx={{
          backdropFilter: "blur(12px)",
          backgroundColor: "rgba(15, 23, 42, 0.82)",
          borderBottom: "1px solid rgba(148, 163, 184, 0.12)",
        }}
      >
        <Toolbar sx={{ minHeight: 72, px: { xs: 2, md: 4 }, gap: 2 }}>
          <Box
            component="img"
            src="/book.svg"
            alt="Library icon"
            sx={{ height: 32, width: 32, borderRadius: "25%", boxShadow: "0 8px 24px rgba(15,23,42,0.35)" }}
          />
          <Tabs
            value={currentTab}
            onChange={(_event, value: number) => setCurrentTab(value)}
            variant="scrollable"
            scrollButtons="auto"
            textColor="inherit"
            TabIndicatorProps={{
              sx: { bgcolor: "primary.light", height: 3, borderRadius: 3 },
            }}
            sx={{
              flexGrow: 1,
              minHeight: 0,
              "& .MuiTabs-flexContainer": {
                gap: { xs: 0.5, md: 1.5 },
              },
            }}
          >
            {tabs.map((tab, index) => (
              <Tab
                key={tab.label}
                icon={tab.icon}
                iconPosition="start"
                label={tab.label}
                sx={{
                  textTransform: "none",
                  minHeight: 0,
                  borderRadius: 999,
                  px: { xs: 1.5, md: 2.5 },
                  py: 1,
                  alignItems: "center",
                  justifyContent: "center",
                  "&.Mui-selected": {
                    bgcolor: "rgba(148, 163, 184, 0.2)",
                    color: "primary.light",
                  },
                }}
                {...tabA11yProps(index)}
              />
            ))}
          </Tabs>
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl">
        {tabs.map((tab, index) => (
          <TabPanel key={tab.label} value={currentTab} index={index}>
            {tab.content}
          </TabPanel>
        ))}
      </Container>
    </Box>
  );
}
